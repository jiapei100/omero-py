#!/usr/bin/env python

"""
   Test of the Tables facility independent of Ice.

   Copyright 2009 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import Ice
import exceptions
import omero, omero.tables
import unittest, sys, os, logging
import tablestest.library as lib

from omero.columns import *
from path import path
from uuid import uuid4

logging.basicConfig(level=logging.CRITICAL)

class communicator_provider(object):
    def __init__(self, ic = None):
        self.ic = ic
    def __call__(self, *args):
        return self.ic

class mock_communicator(object):
    def __init__(self):
        self.delegate  = Ice.initialize()
        for of in ObjectFactories.values():
            of.register(self.delegate) # Columns
    # Delegated
    def getProperties(self):
        return self.delegate.getProperties()
    def findObjectFactory(self, s):
        return self.delegate.findObjectFactory(s)
    # Overriden
    def stringToProxy(self, arg):
        return arg

class mock_current(object):
    def __init__(self, communicator):
        self.adapter = mock_adapter(communicator)

class mock_adapter(object):
    def __init__(self, communicator):
        self.ic = communicator
    def addWithUUID(self, arg):
        return arg
    def getCommunicator(self):
        return self.ic

class mocked_internal_service_factory(object):
    def __init__(self, sf = None):
        if sf == None:
            sf = mocked_service_factory()
        self.sf = sf
    def __call__(self, *args, **kwargs):
        if not self.sf:
            raise exceptions.Exception("Mock error connecting to server")
        return self.sf

class mocked_service_factory(object):
    def __init__(self):
        self.db_uuid = str(uuid4())
        self.return_values = []
    def getConfigService(self):
        return mocked_config_service(self.db_uuid, self.return_values)
    def getQueryService(self):
        return mocked_query_service(self.return_values)
    def destroy(self):
        pass

class mocked_config_service(object):
    def __init__(self, db_uuid, return_values):
        self.db_uuid = db_uuid
        self.return_values = return_values
    def getDatabaseUuid(self):
        return self.db_uuid
    def getConfigValue(self, str):
        rv = self.return_values.pop(0)
        if isinstance(rv, omero.ServerError):
            raise rv
        else:
            return rv

class mocked_query_service(object):
    def __init__(self, return_values):
        self.return_values = return_values
    def findByQuery(self, *args):
        rv = self.return_values.pop(0)
        if isinstance(rv, omero.ServerError):
            raise rv
        else:
            return rv

class mock_internal_repo(object):
    def __init__(self, dir):
        self.path = dir / "mock.h5"
    def __call__(self, *args):
        return self
    def getProxy(self):
        return self
    def getFilePath(self, *args):
        return self.path

class mock_table(object):
    def __call__(self, *args):
        self.table = args[0]
        return self

class mock_storage(object):
    def __init__(self):
        self.up = False
        self.down = False

    def incr(self, *args):
        self.up = True

    def decr(self, *args):
        self.down = True

class TestTables(lib.TestCase):

    def setUp(self):
        lib.TestCase.setUp(self)
        omero.util.internal_service_factory = mocked_internal_service_factory()
        self.sf = omero.util.internal_service_factory.sf
        self.communicator = communicator_provider(mock_communicator())
        self.current = mock_current(self.communicator())
        omero.tables.TablesI.communicator = self.communicator()

    def tablesI(self, internal_repo = None):
        if internal_repo is None:
            internal_repo = mock_internal_repo(self.tmp)
        return omero.tables.TablesI(mock_table(), internal_repo)

    def repouuid(self):
        """
        Returns a string similar to that written by RandomAccessFile.writeUTF() in Java
        """
        return "XX%s" % uuid4()

    def repodir(self, make = True):
        self.tmp = path(self.tmpdir())
        self.communicator().getProperties().setProperty("omero.repo.dir", str(self.tmp))
        repo = self.tmp / ".omero" / "repository"
        if make:
            repo.makedirs()
        return str(repo)

    def repofile(self, db_uuid, repo_uuid=None):
        if repo_uuid == None:
            repo_uuid = self.repouuid()
        f = self.repodir()
        f = path(f) / db_uuid
        f.makedirs()
        f = f / "repo_uuid"
        f.write_lines([repo_uuid])

    # Note: some of the following method were added as __init__ called
    # first _get_dir() and then _get_uuid(), so the naming is off

    def testTablesIGetDirNoRepoSet(self):
        self.sf.return_values.append(self.tmpdir())
        self.assertRaises(omero.ResourceError, omero.tables.TablesI)

    def testTablesIGetDirNoRepoCreated(self):
        self.repodir(False)
        self.assertRaises(omero.ResourceError, omero.tables.TablesI)

    def testTablesIGetDirGetsRepoThenNoSF(self):
        self.repodir()
        omero.util.internal_service_factory = mocked_internal_service_factory(None)
        self.assertRaises(exceptions.Exception, omero.tables.TablesI)

    def testTablesIGetDirGetsRepoGetsSFCantFindRepoFile(self):
        self.repodir()
        self.assertRaises(exceptions.IOError, omero.tables.TablesI)

    def testTablesIGetDirGetsRepoGetsSFCantFindRepoObject(self):
        self.repofile(self.sf.db_uuid)
        self.sf.return_values.append( omero.ApiUsageException(None, None, "Cant Find") )
        self.assertRaises(omero.ApiUsageException, omero.tables.TablesI)

    def testTablesIGetDirGetsRepoGetsSFGetsRepo(self):
        self.repofile(self.sf.db_uuid)
        self.sf.return_values.append( omero.model.OriginalFileI( 1, False) )
        tables = self.tablesI()

    def testTables(self, newfile = True):
        if newfile:
            self.repofile(self.sf.db_uuid)
        f = omero.model.OriginalFileI( 1, False)
        self.sf.return_values.append( f )
        tables = self.tablesI()
        table = tables.getTable(f, self.current)
        self.assert_( table )
        return table

    def testTableIncrDecr(self):
        storage = mock_storage()
        table = omero.tables.TableI(omero.model.OriginalFileI(1,None), storage)
        self.assertTrue(storage.up)
        table.cleanup()
        self.assertTrue(storage.down)

    def testTablePreInitialized(self):
        mocktable = self.testTables()
        table1 = mocktable.table
        storage = table1.storage
        storage.initialize([LongColumnI("a",None,[])])
        table2 = omero.tables.TableI(omero.model.OriginalFileI(1, None), storage)
        table2.cleanup()
        table1.cleanup()

    def testTableModifications(self):
        mocktable = self.testTables()
        table = mocktable.table
        storage = table.storage
        storage.initialize([LongColumnI("a",None,[])])
        self.assertTrue(storage.uptodate(table.stamp))
        storage._stamp += 1 # Not really allowed
        self.assertFalse(storage.uptodate(table.stamp))
        table.cleanup()

    def testTableModifications(self):
        mocktable = self.testTables()
        table = mocktable.table
        storage = table.storage
        storage.initialize([LongColumnI("a",None,[])])
        self.assertTrue(storage.uptodate(table.stamp))
        storage._stamp += 1 # Not really allowed
        self.assertFalse(storage.uptodate(table.stamp))
        table.cleanup()

    def testTableAddData(self, newfile = True, cleanup = True):
        mocktable = self.testTables(newfile)
        table = mocktable.table
        table.initialize([LongColumnI("a", None,[]), DoubleColumnI("b", None, [])])
        template = table.getHeaders(self.current)
        template[0].values = [ 1 ]*5
        template[1].values = [2.0]*5
        table.addData(template)
        if cleanup:
            table.cleanup()
        return table

    def testTableSearch(self):
        table = self.testTableAddData(True, False)
        rv = list(table.getWhereList('(a==1)',None,None,None,None,None))
        self.assertEquals(range(5), rv)
        data = table.readCoordinates(rv, self.current)
        self.assertEquals(2, len(data.columns))
        for i in range(5):
            self.assertEquals(1, data.columns[0].values[i])
            self.assertEquals(2.0, data.columns[1].values[i])
        table.cleanup()

    def testErrorInStorage(self):
        self.repofile(self.sf.db_uuid)
        f = omero.model.OriginalFileI( 1, False)
        self.sf.return_values.append( f )

        internal_repo = mock_internal_repo(self.tmp)
        f = open(internal_repo.path,"w")
        f.write("this file is not HDF")
        f.close()

        tables = self.tablesI(internal_repo)
        self.assertRaises(omero.ValidationException, tables.getTable, f, self.current)

    def testErrorInGet(self):
        self.repofile(self.sf.db_uuid)
        f = omero.model.OriginalFileI( 1, False)
        self.sf.return_values.append( f )
        tables = self.tablesI()
        table = tables.getTable(f, self.current).table # From mock
        cols = [ omero.columns.LongColumnI('name','desc',None) ]
        table.initialize(cols)
        cols[0].values = [1,2,3,4]
        table.addData(cols)
        table.getWhereList('(name==1)',None,0,0,0,self.current)

def test_suite():
    return 1

if __name__ == '__main__':
    if "profile" in sys.argv:
        sys.argv.remove("profile")
        import cProfile
        cProfile.run("unittest.main()", sort=3)
        # stats.strip_dirs().sort_stats('time').print_stats(20)
    else:
        unittest.main()