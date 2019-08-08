class CollInfo {
    constructor(conn, connName, collInfos, dbName, collName) {
        assert.eq(Array.isArray(collInfos), true, 'collInfos must be an array or omitted');

        this.conn = conn;
        this.connName = connName;
        this.collInfos = collInfos;
        this.collName = collName;
        this.dbName = dbName;
    }

    ns() {
        return this.dbName + '.' + this.collName;
    }

    hostAndNS() {
        return `${this.conn.host}--${this.ns()}`;
    }

    print(collectionPrinted) {
        const alreadyPrinted = collectionPrinted.has(this.hostAndNS());

        // Extract basic collection info.
        const coll = conn.getDB(dbName).getCollection(collName);
        let collInfo = null;

        const collInfoRaw = this.collInfos.find(elem => elem.name === collName);
        if (collInfoRaw) {
            collInfo = {
                ns: ns,
                host: conn.host,
                UUID: collInfoRaw.info.uuid,
                count: coll.find().itcount()
            };
        }

        const infoPrefix = `${this.connName}(${this.conn.host}) info for ${this.ns()} : `;
        if (collInfo !== null) {
            if (alreadyPrinted) {
                print(`${this.connName} info for ${this.ns()} already printed. Search for ` +
                      `'${infoPrefix}'`);
            } else {
                print(infoPrefix + tojsononeline(collInfo));
            }
        } else {
            print(infoPrefix + 'collection does not exist');
        }

        const collStats = conn.getDB(this.dbName).runCommand({collStats: this.collName});
        const statsPrefix = `${this.connName}(${this.conn.host}) collStats for ${this.ns()}: `;
        if (collStats.ok === 1) {
            if (alreadyPrinted) {
                print(`${this.connName} collStats for ${this.ns()} already printed. Search for ` +
                      `'${statsPrefix}'`);
            } else {
                print(statsPrefix + tojsononeline(collStats));
            }
        } else {
            print(`${statsPrefix}  error: ${tojsononeline(collStats)}`);
        }

        collectionPrinted.add(this.hostAndNS());

        // Return true if collInfo & collStats can be retrieved for conn.
        return collInfo !== null && collStats.ok === 1;
    }
}

class DataConsistencyChecker {
    static dumpCollectionDiff(
        rst, collectionPrinted, primaryCollInfo, secondaryCollInfo, dbName, collName) {
        var ns = dbName + '.' + collName;
        print('Dumping collection: ' + ns);

        const primaryExists = primaryCollInfo.print(collectionPrinted);
        const secondaryExists = secondaryCollInfo.print(collectionPrinted);

        if (!primaryExists || !secondaryExists) {
            print(`Skipping checking collection differences for ${ns} since it does not ` +
                  'exist on primary and secondary');
            return;
        }

        const primary = primaryCollInfo.conn;
        const secondary = secondaryCollInfo.conn;

        const primarySession = primary.getDB('test').getSession();
        const secondarySession = secondary.getDB('test').getSession();
        const diff =
            rst.getCollectionDiffUsingSessions(primarySession, secondarySession, dbName, collName);

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