class CollInfo {
    /**
     *
     * @param conn
     * @param collInfos
     */
    constructor(conn, collInfos) {
        this.conn = conn;
        this.collInfos = collInfos;
    }

    printCollectionInfo(connName, conn, dbName, collName, collInfos) {
        var ns = dbName + '.' + collName;
        var hostColl = `${conn.host}--${ns}`;
        var alreadyPrinted = collectionPrinted.has(hostColl);

        // Extract basic collection info.
        var coll = conn.getDB(dbName).getCollection(collName);
        var collInfo = null;

        // If collInfos is not passed in, call listCollections ourselves.
        if (collInfos === undefined) {
            const res =
                conn.getDB(dbName).runCommand({listCollections: 1, filter: {name: collName}});
            if (res.ok === 1 && res.cursor.firstBatch.length !== 0) {
                collInfo = {
                    ns: ns,
                    host: conn.host,
                    UUID: res.cursor.firstBatch[0].info.uuid,
                    count: coll.find().itcount()
                };
            }
        } else {
            assert.eq(Array.isArray(collInfos), true, 'collInfos must be an array or omitted');
            const collInfoRaw = collInfos.find(elem => elem.name === collName);
            if (collInfoRaw) {
                collInfo = {
                    ns: ns,
                    host: conn.host,
                    UUID: collInfos.info.uuid,
                    count: coll.find().itcount()
                };
            }
        }

        var infoPrefix = `${connName}(${conn.host}) info for ${ns} : `;
        if (collInfo !== null) {
            if (alreadyPrinted) {
                print(`${connName} info for ${ns} already printed. Search for ` +
                    `'${infoPrefix}'`);
            } else {
                print(infoPrefix + tojsononeline(collInfo));
            }
        } else {
            print(infoPrefix + 'collection does not exist');
        }

        var collStats = conn.getDB(dbName).runCommand({collStats: collName});
        var statsPrefix = `${connName}(${conn.host}) collStats for ${ns}: `;
        if (collStats.ok === 1) {
            if (alreadyPrinted) {
                print(`${connName} collStats for ${ns} already printed. Search for ` +
                    `'${statsPrefix}'`);
            } else {
                print(statsPrefix + tojsononeline(collStats));
            }
        } else {
            print(`${statsPrefix}  error: ${tojsononeline(collStats)}`);
        }

        collectionPrinted.add(hostColl);

        // Return true if collInfo & collStats can be retrieved for conn.
        return collInfo !== null && collStats.ok === 1;
    }
}

class DataConsistencyChecker {
    static dumpCollectionDiff(rst, primary, secondary, dbName, collName) {
        var ns = dbName + '.' + collName;
        print('Dumping collection: ' + ns);

        var primaryExists = printCollectionInfo('primary', primary, dbName, collName);
        var secondaryExists = printCollectionInfo('secondary', secondary, dbName, collName);

        if (!primaryExists || !secondaryExists) {
            print(`Skipping checking collection differences for ${ns} since it does not ` +
                'exist on primary and secondary');
            return;
        }

        const primarySession = primary.getDB('test').getSession();
        const secondarySession = secondary.getDB('test').getSession();
        const diff = rst.getCollectionDiffUsingSessions(
            primarySession, secondarySession, dbName, collName);

        for (let {
            primary: primaryDoc,
            secondary: secondaryDoc,
        } of diff.docsWithDifferentContents) {
            print(`Mismatching documents between the primary ${primary.host}` +
                ` and the secondary ${secondary.host}:`);
            print('    primary:   ' + tojsononeline(primaryDoc));
            print('    secondary: ' + tojsononeline(secondaryDoc));
        }

        if (diff.docsMissingOnPrimary.length > 0) {
            print(`The following documents are missing on the primary ${primary.host}:`);
            print(diff.docsMissingOnPrimary.map(doc => tojsononeline(doc)).join('\n'));
        }

        if (diff.docsMissingOnSecondary.length > 0) {
            print(`The following documents are missing on the secondary ${secondary.host}:`);
            print(diff.docsMissingOnSecondary.map(doc => tojsononeline(doc)).join('\n'));
        }
    }
}