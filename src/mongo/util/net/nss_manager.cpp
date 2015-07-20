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

#define MONGO_LOG_DEFAULT_COMPONENT ::mongo::logger::LogComponent::kNetwork

#include "mongo/platform/basic.h"

#include <nspr4/prio.h>
#include <nspr4/private/pprio.h> // :(
#include <nss3/ssl.h>

#include "mongo/util/net/ssl_manager.h"

#include <boost/date_time/posix_time/posix_time.hpp>
#include <boost/thread/recursive_mutex.hpp>
#include <boost/thread/tss.hpp>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "mongo/base/init.h"
#include "mongo/bson/bsonobjbuilder.h"
#include "mongo/config.h"
#include "mongo/stdx/memory.h"
#include "mongo/util/concurrency/mutex.h"
#include "mongo/util/exit.h"
#include "mongo/util/debug_util.h"
#include "mongo/util/log.h"
#include "mongo/util/mongoutils/str.h"
#include "mongo/util/net/sock.h"
#include "mongo/util/net/ssl_options.h"
#include "mongo/util/scopeguard.h"

using std::endl;

namespace mongo {

SSLParams sslGlobalParams;

SSLManagerInterface* theSSLManager = NULL;

SimpleMutex sslManagerMtx;

class SSLConnectionImpl {
public:
    SSLConnectionImpl(PRFileDesc* sslFD) : sslFD(sslFD) {}
    PRFileDesc* sslFD;
};

SSLConnection::SSLConnection(std::unique_ptr<SSLConnectionImpl> impl) : impl(std::move(impl)) {}
SSLConnection::~SSLConnection() {}

class NSSManager : public SSLManagerInterface {
public:
    explicit NSSManager(const SSLParams& params, bool isServer);

    virtual SSLConnection* connect(Socket* socket);

    virtual SSLConnection* accept(Socket* socket, const char* initialBytes, int len);

    virtual std::string parseAndValidatePeerCertificate(const SSLConnection* conn,
                                                        const std::string& remoteHost);

    virtual void cleanupThreadLocals();

    virtual const SSLConfiguration& getSSLConfiguration() const {
        return _sslConfiguration;
    }

    virtual int SSL_read(SSLConnection* conn, void* buf, int num);

    virtual int SSL_write(SSLConnection* conn, const void* buf, int num);

    virtual unsigned long ERR_get_error();

    virtual char* ERR_error_string(unsigned long e, char* buf);

    virtual int SSL_get_error(const SSLConnection* conn, int ret);

    virtual int SSL_shutdown(SSLConnection* conn);

    virtual void SSL_free(SSLConnection* conn);

private:
    std::string _password;
    bool _weakValidation;
    bool _allowInvalidCertificates;
    bool _allowInvalidHostnames;
    SSLConfiguration _sslConfiguration;
};


SSLManagerInterface* getSSLManager() {
    return theSSLManager;
}

// Global variable indicating if this is a server or a client instance
bool isSSLServer = false;

MONGO_INITIALIZER(SetupNSS)(InitializerContext*) {
    return Status::OK();
}

MONGO_INITIALIZER_WITH_PREREQUISITES(SSLManager, ("SetupNSS"))
(InitializerContext*) {
    stdx::lock_guard<SimpleMutex> lck(sslManagerMtx);
    if (sslGlobalParams.sslMode.load() != SSLParams::SSLMode_disabled) {
        theSSLManager = new NSSManager(sslGlobalParams, isSSLServer);
    }
    return Status::OK();
}

std::unique_ptr<SSLManagerInterface> SSLManagerInterface::create(const SSLParams& params,
                                                                 bool isServer) {
    return stdx::make_unique<NSSManager>(params, isServer);
}

SSLManagerInterface* getNSSManager() {
    stdx::lock_guard<SimpleMutex> lck(sslManagerMtx);
    if (theSSLManager)
        return theSSLManager;
    return NULL;
}

BSONObj SSLConfiguration::getServerStatusBSON() const {
    BSONObjBuilder security;
    security.append("SSLServerSubjectName", serverSubjectName);
    security.appendBool("SSLServerHasCertificateAuthority", hasCA);
    security.appendDate("SSLServerCertificateExpirationDate", serverCertificateExpirationDate);
    return security.obj();
}

SSLManagerInterface::~SSLManagerInterface() {}

NSSManager::NSSManager(const SSLParams& params, bool isServer) {}

int NSSManager::SSL_read(SSLConnection* conn, void* buf, int num) {
    return PR_Read(conn->impl->sslFD, buf, num);
}

int NSSManager::SSL_write(SSLConnection* conn, const void* buf, int num) {
    return PR_Write(conn->impl->sslFD, buf, num);
}

unsigned long NSSManager::ERR_get_error() { return 0; }

char* NSSManager::ERR_error_string(unsigned long e, char* buf) { return nullptr; }

int NSSManager::SSL_get_error(const SSLConnection* conn, int ret) { return 0; }

int NSSManager::SSL_shutdown(SSLConnection* conn) { return 0; }

void NSSManager::SSL_free(SSLConnection* conn) {}

SSLConnection* NSSManager::connect(Socket* socket) {
    PRFileDesc* prFD = PR_ImportTCPSocket(socket->rawFD());
    PRFileDesc* sslFD = SSL_ImportFD(nullptr, prFD);
    auto sslConnImpl = stdx::make_unique<SSLConnectionImpl>(sslFD);
    auto sslConn = stdx::make_unique<SSLConnection>(std::move(sslConnImpl));

    return sslConn.release();
}

SSLConnection* NSSManager::accept(Socket* socket, const char* initialBytes, int len) {
    PRFileDesc* prFD = PR_ImportTCPSocket(socket->rawFD());
    PRFileDesc* sslFD = SSL_ImportFD(nullptr, prFD);
    massert(ErrorCodes::BadValue, "Could not require certificate",
            SECSuccess == SSL_OptionSet(sslFD, SSL_REQUEST_CERTIFICATE, PR_TRUE));
    auto sslConnImpl = stdx::make_unique<SSLConnectionImpl>(sslFD);
    auto sslConn = stdx::make_unique<SSLConnection>(std::move(sslConnImpl));
    return sslConn.release();
}

std::string NSSManager::parseAndValidatePeerCertificate(const SSLConnection* conn,
                                                        const std::string& remoteHost) {
    return "";
}

void NSSManager::cleanupThreadLocals() {
}

std::string SSLManagerInterface::getSSLErrorMessage(int code) {
    return "";
}

} // namespace mongo
