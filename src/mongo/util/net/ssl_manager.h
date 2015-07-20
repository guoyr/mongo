/*    Copyright 2009 10gen Inc.
 *
 *    This program is free software: you can redistribute it and/or  modify
 *    it under the terms of the GNU Affero General Public License, version 3,
 *    as published by the Free Software Foundation.
 *
 *    This program is distributed in the hope that it will be useful,
 *    but WITHOUT ANY WARRANTY; without even the implied warranty of
 *    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *    GNU Affero General Public License for more details.
 *
 *    You should have received a copy of the GNU Affero General Public License
 *    along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 *    As a special exception, the copyright holders give permission to link the
 *    code of portions of this program with the OpenSSL library under certain
 *    conditions as described in each individual source file and distribute
 *    linked combinations including the program with the OpenSSL library. You
 *    must comply with the GNU Affero General Public License in all respects
 *    for all of the code used other than as permitted herein. If you modify
 *    file(s) with this exception, you may extend this exception to your
 *    version of the file(s), but you are not obligated to do so. If you do not
 *    wish to do so, delete this exception statement from your version. If you
 *    delete this exception statement from all source files in the program,
 *    then also delete it in the license file.
 */

#pragma once

#include <memory>
#include <string>

#include "mongo/config.h"

#ifdef MONGO_CONFIG_SSL

#include "mongo/base/disallow_copying.h"
#include "mongo/bson/bsonobj.h"
#include "mongo/util/net/sock.h"
#include "mongo/util/time_support.h"

namespace mongo {
struct SSLParams;

class SSLConnectionImpl;
class SSLConnection {
public:
    SSLConnection(std::unique_ptr<SSLConnectionImpl> impl);
    ~SSLConnection();
    std::unique_ptr<SSLConnectionImpl> impl;
};


struct SSLConfiguration {
    SSLConfiguration() : serverSubjectName(""), clientSubjectName(""), hasCA(false) {}
    SSLConfiguration(const std::string& serverSubjectName,
                     const std::string& clientSubjectName,
                     const Date_t& serverCertificateExpirationDate,
                     bool hasCA)
        : serverSubjectName(serverSubjectName),
          clientSubjectName(clientSubjectName),
          serverCertificateExpirationDate(serverCertificateExpirationDate),
          hasCA(hasCA) {}

    BSONObj getServerStatusBSON() const;
    std::string serverSubjectName;
    std::string clientSubjectName;
    Date_t serverCertificateExpirationDate;
    bool hasCA;
};

class SSLManagerInterface {
public:
    static std::unique_ptr<SSLManagerInterface> create(const SSLParams& params, bool isServer);

    virtual ~SSLManagerInterface();

    /**
     * Initiates a TLS connection.
     * Throws SocketException on failure.
     * @return a pointer to an SSLConnection. Resources are freed in SSLConnection's destructor
     */
    virtual SSLConnection* connect(Socket* socket) = 0;

    /**
     * Waits for the other side to initiate a TLS connection.
     * Throws SocketException on failure.
     * @return a pointer to an SSLConnection. Resources are freed in SSLConnection's destructor
     */
    virtual SSLConnection* accept(Socket* socket, const char* initialBytes, int len) = 0;

    /**
     * Fetches a peer certificate and validates it if it exists
     * Throws SocketException on failure
     * @return a std::string containing the certificate's subject name.
     */
    virtual std::string parseAndValidatePeerCertificate(const SSLConnection* conn,
                                                        const std::string& remoteHost) = 0;

    /**
     * Cleans up SSL thread local memory; use at thread exit
     * to avoid memory leaks
     */
    virtual void cleanupThreadLocals() = 0;

    /**
     * Gets the SSLConfiguration containing all information about the current SSL setup
     * @return the SSLConfiguration
     */
    virtual const SSLConfiguration& getSSLConfiguration() const = 0;

    /**
    * Fetches the error text for an error code, in a thread-safe manner.
    */
    static std::string getSSLErrorMessage(int code);

    /**
     * ssl.h wrappers
     */
    virtual int SSL_read(SSLConnection* conn, void* buf, int num) = 0;

    virtual int SSL_write(SSLConnection* conn, const void* buf, int num) = 0;

    virtual unsigned long ERR_get_error() = 0;

    virtual char* ERR_error_string(unsigned long e, char* buf) = 0;

    virtual int SSL_get_error(const SSLConnection* conn, int ret) = 0;

    virtual int SSL_shutdown(SSLConnection* conn) = 0;

    virtual void SSL_free(SSLConnection* conn) = 0;
};

// Access SSL functions through this instance.
SSLManagerInterface* getSSLManager();

extern bool isSSLServer;
}
#endif  // #ifdef MONGO_CONFIG_SSL
