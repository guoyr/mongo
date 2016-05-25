// Runner for checkReplicationConsistency() that runs the dbhash command on all replica set nodes
// to ensure all nodes have the same data.
'use strict';

(function() {
    // A thin wrapper around master/slave nodes that provides the getHashes(), getPrimary(),
    // awaitReplication(), and nodeList() methods. Note that this wrapper only supports nodes
    // started through resmoke's masterslave.py fixture.
    var MasterSlaveDBHashTest = function(primaryHost) {
        var master = new Mongo(primaryHost);
        var resolvedHost = getHostName();
        var masterPort = master.host.split(':')[1];
        master.host = resolvedHost + ':' + masterPort;

        var slave = new Mongo(resolvedHost + ':' + String(Number(masterPort) + 1));

        this.nodeList = function() {
            return [master.host, slave.host];
        };

        this.getHashes = function(db) {
            var combinedRes = {};
            var res = master.getDB(db).runCommand("dbhash");
            assert.commandWorked(res);
            combinedRes.master = res;

            res = slave.getDB(db).runCommand("dbhash");
            assert.commandWorked(res);
            combinedRes.slaves = [res];

            return combinedRes;
        };

        this.getPrimary = function() {
            slave.setSlaveOk();
            this.liveNodes = {
                master: master,
                slaves: [slave]
            };

            return master;
        };

        this.awaitReplication = function() {};
    };

    var startTime = Date.now();
    assert.neq(typeof db, 'undefined', 'No `db` object, is the shell connected to a mongod?');

    var primaryInfo = db.isMaster();

    assert(primaryInfo.ismaster,
           'shell is not connected to the primary or master node: ' + tojson(primaryInfo));

    var rst;
    var cmdLineOpts = db.adminCommand('getCmdLineOpts');
    assert.commandWorked(cmdLineOpts);
    var isMasterSlave = cmdLineOpts.parsed.master === true;
    if (isMasterSlave) {
        rst = new MasterSlaveDBHashTest(db.getMongo().host);
    } else {
        rst = new ReplSetTest(db.getMongo().host);
    }

    // Call getPrimary to populate rst with information about the nodes.
    var primary = rst.getPrimary();
    assert(primary, 'calling ReplSetTest.getPrimary() failed');

    var activeException = false;

    try {
        // Lock the primary to prevent the TTL monitor from deleting expired documents in
        // the background while we are getting the dbhashes of the replica set members.
        assert.commandWorked(primary.adminCommand({fsync: 1, lock: 1}),
                             'failed to lock the primary');
        rst.awaitReplication();

        var phaseName = 'after test hook';
        load('jstests/hooks/check_repl_dbhash.js');
        var blacklist = [];
        checkDBHashes(rst, blacklist, phaseName);
    } catch (e) {
        activeException = true;
        throw e;
    } finally {
        // Allow writes on the primary.
        var res = primary.adminCommand({fsyncUnlock: 1});

        if (!res.ok) {
            var msg = 'failed to unlock the primary, which may cause this' +
                ' test to hang: ' + tojson(res);
            if (activeException) {
                print(msg);
            } else {
                throw new Error(msg);
            }
        }
    }

    var totalTime = Date.now() - startTime;
    print('Finished consistency checks of cluster in ' + totalTime + ' ms.');
})();
