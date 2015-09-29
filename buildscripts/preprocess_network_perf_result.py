import sys
import argparse
import json

from dateutil import parser
from datetime import timedelta, datetime

# Extracts throughput from network_interface_perf_test and appends it to perf.json

# read log output from network perf data and write to a dictionary of {testName: ops/s}
def parseNetworkPerfData(dataFd):
    results = {"start": None, "end": None, "data": {}}
    for line in dataFd.readlines():
        try:
            date = parser.parse(line)
            date = date.replace(tzinfo=None)
            if results["start"]:
                results["end"] = date
            else:
                results["start"] = date
        except Exception:
            pass

        if line.find("THROUGHPUT") != -1:
            kv = line.split(": ")
            if len(kv) == 2:
                results["data"][kv[0]] = int(kv[1])

    return results


# construct a document from the network perf data and append it to the perf document
def addNetworkPerfData(networkPerfData, allPerfData):

    for name in networkPerfData["data"].keys():
        throughput = networkPerfData["data"][name]
        networkPerfDoc = {
            "name": name.split("THROUGHPUT")[1],
            "results": {
                "start": networkPerfData["start"].isoformat(),
                "end": networkPerfData["end"].isoformat(),
                "1": {
                    "ops_per_sec": throughput,
                    "ops_per_sec_values": [throughput],
                    "error_values": [0]
                }
            }
        }

        allPerfData["results"].append(networkPerfDoc)

def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--data", dest="data", help="path to output of network_perf_result file")
    parser.add_argument("-p", "--perf-data", dest="allPerfData", help="path to json file containing history data")

    args = parser.parse_args()

    # allPerfData may not exist if we don't run the other perf suites
    try:
        with open(args.allPerfData) as f1:
            allPerfData = json.load(f1)
    except IOError:
        allPerfData = {"results": []}

    networkPerfData = parseNetworkPerfData(open(args.data))

    addNetworkPerfData(networkPerfData, allPerfData)

    json.dump(allPerfData, open(args.allPerfData, 'w'), indent=4, separators=(',', ': '))



if __name__ == '__main__':
    main(sys.argv[1:])