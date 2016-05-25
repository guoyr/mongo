// Check that the dbhashes of all the nodes in a ReplSetTest are consistent.
'use strict';

// Return objects in either Array `a` or `b` but not both.
function arraySymmetricDifference(a, b) {
    var inA = a.filter(function(elem) {
        return b.indexOf(elem) < 0;
    });

    var inB = b.filter(function(elem) {
        return a.indexOf(elem) < 0;
    });

    return [].concat(inA).concat(inB);
}

function dumpCollectionDiff(primary, secondary, dbName, collName) {
    print('Dumping collection: ' + dbName + '.' + collName);

    var primaryColl = primary.getDB(dbName).getCollection(collName);
    var secondaryColl = secondary.getDB(dbName).getCollection(collName);

    var primaryDocs = primaryColl.find().sort({_id: 1}).toArray();
    var secondaryDocs = secondaryColl.find().sort({_id: 1}).toArray();

    var primaryIndex = primaryDocs.length - 1;
    var secondaryIndex = secondaryDocs.length - 1;

    var missingOnPrimary = [];
    var missingOnSecondary = [];

    while (primaryIndex >= 0 || secondaryIndex >= 0) {
        var primaryDoc = primaryDocs[primaryIndex];
        var secondaryDoc = secondaryDocs[secondaryIndex];

        if (primaryIndex < 0) {
            missingOnPrimary.push(tojsononeline(secondaryDoc));
            secondaryIndex--;
        } else if (secondaryIndex < 0) {
            missingOnSecondary.push(tojsononeline(primaryDoc));
            primaryIndex--;
        } else {
            if (bsonWoCompare(primaryDoc, secondaryDoc) !== 0) {
                print('Mismatching documents:');
                print('    primary: ' + tojsononeline(primaryDoc));
                print('    secondary: ' + tojsononeline(secondaryDoc));
                var ordering =
                    bsonWoCompare({wrapper: primaryDoc._id}, {wrapper: secondaryDoc._id});
                if (ordering === 0) {
                    primaryIndex--;
                    secondaryIndex--;
                } else if (ordering < 0) {
                    missingOnPrimary.push(tojsononeline(secondaryDoc));
                    secondaryIndex--;
                } else if (ordering > 0) {
                    missingOnSecondary.push(tojsononeline(primaryDoc));
                    primaryIndex--;
                }
            } else {
                // Latest document matched.
                primaryIndex--;
                secondaryIndex--;
            }
        }
    }

    if (missingOnPrimary.length) {
        print('The following documents are missing on the primary:');
        print(missingOnPrimary.join('\n'));
    }
    if (missingOnSecondary.length) {
        print('The following documents are missing on the secondary:');
        print(missingOnSecondary.join('\n'));
    }
}

function checkDBHashes(rst, dbBlacklist, phase) {
    // We don't expect the local database to match as some of its collections are not replicated.
    dbBlacklist.push('local');

    // Use liveNodes.master instead of getPrimary() to avoid the detection of a new primary.
    // liveNodes must have been populated.
    var primary = rst.liveNodes.master;

    var res = primary.adminCommand({listDatabases: 1});
    assert.commandWorked(res);

    var success = true;
    var hasDumpedOplog = false;

    res.databases.forEach(dbInfo => {
        var dbName = dbInfo.name;
        if (Array.contains(dbBlacklist, dbName)) {
            return;
        }

        var dbHashes = rst.getHashes(dbName);
        var primaryDBHash = dbHashes.master;
        assert.commandWorked(primaryDBHash);

        dbHashes.slaves.forEach(secondaryDBHash => {
            assert.commandWorked(secondaryDBHash);
            // TODO: uncomment this after SERVER-21762 is pushed.
            // assert.eq(primaryDBHash.exists, secondaryDBHash.exists,
            //           'db does not exist on either the primary or the secondary');

            var secondary = rst.liveNodes.slaves.find(e => e.host === secondaryDBHash.host);
            assert(secondary,
                   'could not find replica set secondary in dbhash response ' +
                       tojson(secondaryDBHash));

            var primaryCollections = Object.keys(primaryDBHash.collections);
            var secondaryCollections = Object.keys(secondaryDBHash.collections);

            if (primaryCollections.length !== secondaryCollections.length) {
                print(phase +
                      ', the primary and secondary have a different number of collections: ' +
                      tojson(dbHashes));
                if (success) {
                    for (var diffColl of
                             arraySetDifference(primaryCollections, secondaryCollections)) {
                        dumpCollectionDiff(primary, secondary, dbName, diffColl);
                    }
                    success = false;
                }
            }

            var collNames =
                Object.keys(primaryDBHash.collections)
                    .filter(collName => !primary.getDB(dbName).getCollection(collName).isCapped());
            if (success) {
                // Only compare the dbhashes of non-capped collections because capped collections
                // are not necessarily truncated at the same points across replica set members.
                collNames.forEach(collName => {
                    if (primaryDBHash.collections[collName] !==
                        secondaryDBHash.collections[collName]) {
                        print(phase + ', the primary and secondary have a different hash for the' +
                              ' collection ' + dbName + '.' + collName + ': ' + tojson(dbHashes));
                        dumpCollectionDiff(primary, secondary, dbName, collName);
                        success = false;
                    }

                });
            }

            if (success && collNames.length === primaryCollections.length) {
                // If the primary and secondary have the same hashes for all the collections in
                // the database and there aren't any capped collections, then the hashes for the
                // whole database should match.
                if (primaryDBHash.md5 !== secondaryDBHash.md5) {
                    print(phase + ', the primary and secondary have a different hash for the ' +
                          dbName + ' database: ' + tojson(dbHashes));
                    success = false;
                }
            }

            if (!success) {
                var dumpOplog = function(conn, limit) {
                    var cursor = conn.getDB('local')
                                     .getCollection('oplog.rs')
                                     .find()
                                     .sort({$natural: -1})
                                     .limit(limit);
                    while (cursor.hasNext()) {
                        print(tojsononeline(cursor.next()));
                    }
                };

                if (!hasDumpedOplog) {
                    print('Dumping the latest 100 documents from the primary\'s oplog:');
                    dumpOplog(primary, 100);
                    print('Dumping the latest 100 documents from the secondary\'s oplog:');
                    dumpOplog(secondary, 100);
                    hasDumpedOplog = true;
                }
            }
        });
    });

    assert(success, 'dbhash mismatch between primary and secondary');
}
