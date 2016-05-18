# -*- coding: utf-8 -*-
"""
twisted-server.py
~~~~~~~~~~~~~~~~~

A fully-functional HTTP/2 server written for Twisted.
"""
import functools
import mimetypes
import os
import os.path
import sys

from OpenSSL import crypto
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import endpoints
from twisted.internet import reactor, ssl
from h2.connection import H2Connection
from h2.events import (
    RequestReceived, DataReceived, StreamEnded, WindowUpdated
)
from h2.errors import PROTOCOL_ERROR

from twisted.web import server, resource
import json
import MySQLdb
import collections
import io
import requests

RequestData = collections.namedtuple('RequestData', ['headers', 'data'])

class H2Protocol(Protocol):
    def __init__(self, root):
        self.conn = H2Connection(client_side=False)
        self.known_proto = None
        self.root = root
        self.stream_data = {}
        self.s_body = {}
        self.invalid_method = False
        self.error = False
        self.post_type = 'None'
        self.success = False
        self.failure = False

        # this hard-coded URL simulates the Client address
        self.url = 'https://httpbin.org/post' 
        
        # hard-coded values to send in success/failure POST
        self.post_data_success = '{"user":"bro","login":"success"}'
        self.post_data_failure = '{"user":"bro","login":"failure"}'

        self._flow_control_deferreds = {}

    def connectionMade(self):
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())

    def dataReceived(self, data):
        if not self.known_proto:
            self.known_proto = True

        events = self.conn.receive_data(data)
        if self.conn.data_to_send:
            self.transport.write(self.conn.data_to_send())

        for event in events:
            if isinstance(event, RequestReceived):
                self.requestReceived(event.headers, event.stream_id)
            elif isinstance(event, DataReceived):
                self.dataFrameReceived(event.stream_id, event.data)
            elif isinstance(event, StreamEnded):
                self.streamComplete(event.stream_id)                
        self.transport.write(self.conn.data_to_send()) 

    def requestReceived(self, headers, stream_id):
        headers = collections.OrderedDict(headers)
        method = headers[':method']

        # Return 405 status if user sends anything other than GET or POST
        if method not in ('GET', 'POST'):
            self.return_XXX('405', stream_id)
            print "Unsupported request method '%s'" % method
            self.invalid_method = True
            return        

        path = headers[':path'].lstrip('/')
        print "Given path: ", path
        
        # Return 404 status if user sends an empty path with request
        if not path:
            print "Nothing to fetch in path '%s'" % path
            self.error = True
            return

        request_data = RequestData(headers, io.BytesIO())
        self.stream_data[stream_id] = request_data
            
        if headers[':method'] == 'POST':
            print '--RECEIVED POST'
            self.validate_POST(path, headers, stream_id)    
        elif headers[':method'] == 'GET':
            print '--RECEIVED GET' 
            self.handle_GET(path, stream_id)
        
        print "Done handling request."
        return

    def validate_POST(self, path, headers, stream_id):
        if 'register' in path:
            print "REGISTER new user!"
            self.post_type = 'register'
            
        elif 'update' in path:
            print "UPDATE user token!"
            self.post_type = 'update'
                    
        elif 'login' in path:
            print "LOG IN!"
            self.post_type = 'login'
            
        elif 'success' in path:
            print "SUCCESSFUL login!"
            self.post_type = 'success'
            
        elif 'failure' in path:
            print "FAILED login!"
            self.post_type = 'failure'
                        
        else:
            print "BOGUS path"
            self.error = True
        
        print "POST validated as '%s'." % self.post_type
    
    def handle_POST(self, data, stream_id):
        
        #########################################
        # THIS OCCURS WHEN USER FIRST REGISTERS #
        #########################################    
        if 'register' in self.post_type:
            print "...REGISTER new user!"

            try:
                stream_data = self.stream_data[stream_id]
            except KeyError:
                self.conn.reset_stream(stream_id, error_code=PROTOCOL_ERROR)
            else:
                stream_data.data.write(data)
            
            try:
                jdata = json.loads(data)                
                
                print "  username: " + jdata["username"]
                print "  email: " + jdata["email"]
                print "  token: " + jdata["token"]
                
                # if user is already registered, the POST should fail
                if self.db_validate(jdata["username"]) is not None:
                    print "ALREADY REGISTERED!"
                    self.error = True
                    return                
                
                self.db_set(jdata, stream_id)
            except KeyError:
                print "=-=-= Invalid POST with register!"
    #            self.conn.reset_stream(stream_id, error_code=PROTOCOL_ERROR)            
                pass

        #########################################
        # THIS OCCURS WHEN USER IS VERIFIED     #
        ######################################### 
        if 'update' in self.post_type:
            print "...UPDATE new user's TOKEN!"

            try:
                stream_data = self.stream_data[stream_id]
            except KeyError:
                self.conn.reset_stream(stream_id, error_code=PROTOCOL_ERROR)
            else:
                stream_data.data.write(data)

            try:
                jdata = json.loads(data)                
                
                print "  username: " + jdata["username"]
                print "  email: " + jdata["email"]
                print "  token: " + jdata["token"]
                
                # if user is not registered, the POST should fail
                if self.db_validate(jdata["username"]) is not None:
                    print "USER FOUND!"
                    self.db_update(jdata, stream_id)
                    
                else:
                    print "CAN'T UPDATE NON-EXISTENT USER!"
                    self.error = True
                    return                

            except KeyError:
                print "=-=-= Invalid POST with update!"           
                pass
                
        #################################
        # THIS IS WHERE WE CALL THE APN #
        #################################    
        elif 'login' in self.post_type:
            print "...LOG IN user!"
            
            # NOT YET IMPLEMENTED
            self.error = True
            return

        ####################################################
        # THIS IS WHERE WE RETURN LOGIN SUCCESS TO CLIENT  #
        # using a POST to the Client with a 'success' str  #
        ####################################################   
        elif 'success' in self.post_type:
            print "...SUCCESSFUL login for user!"
            self.send_POST(self.post_data_success)        
            self.success = True   
            
        elif 'failure' in self.post_type:
            print "...FAILED login for user!"            
            self.send_POST(self.post_data_failure)        
            self.failure = True
            
        print "POST complete."

    # the POST send to notify Client of user's successful/failed authentication
    def send_POST(self, response):
        hdrs = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        request = requests.post(self.url, data=response, headers=hdrs)
        status = request.status_code
        jdata = json.dumps(request.json())
        
        print "    Status code = ", status
        print "    Data: ", jdata
    
    def handle_GET(self, path, stream_id):     
        if ("user" in path):
            print "GET user request with '%s'" % path

            uname = path.split('/')[-1]               

            if uname and (uname not in 'user'):
                # if user is not found, the GET should fail
                if self.db_validate(uname) is None:
                    print "NOT IN DB!"
                    self.error = True
                    return

                to_send = self.db_get(uname)
                
                print "about to send %s" % to_send
                request_data = self.stream_data[stream_id]
                self.s_body = to_send
                print "-->", json.loads(self.s_body)
            
                try:
                    stream_data = self.stream_data[stream_id]
                except KeyError:
                    print "GET KeyError..."
                    self.conn.reset_stream(stream_id, error_code=PROTOCOL_ERROR)
                else:
                    stream_data.data.write(to_send)
            else:
                print "=== NO username provided!"
                self.error = True
                return
        else:
            print "=== Invalid username provided!"
            self.error = True
            return    
            
            print "GET complete."
        
    def dataFrameReceived(self, stream_id, data):
        """
        Pull data from stream or reset if data not expected.
        """
        print "in dataFrameReceived."
        
        if self.error:
            print "   skipping due to error flag..."
            return
        else:
            self.handle_POST(data, stream_id)
        print "Done with dataFrameReceived."
        
    def streamComplete(self, stream_id):
        """
        Complete response and send out.
        """
        print "in streamComplete"
        
        if self.invalid_method:
            print "    skipping due to invalid method."
            return
        if self.error:
            print "   skipping due to error flag."
            self.errorFound(stream_id)
            return
        elif self.success or self.failure:
            print "   success/failure flag, return 200"
            data = ''
            
        else:
            try:
                request_data = self.stream_data[stream_id]
            except KeyError:
                print "Yikes in streamComplete."
                return

            headers = request_data.headers
            body = json.loads(request_data.data.getvalue().decode('utf-8'))
            
            if headers[':method'] == 'GET':        
                data = json.dumps(body).encode("utf8") 

            elif headers[':method'] == 'POST':
                data = ''
        
        response_headers = self.return_200(data)
        self.conn.send_headers(stream_id, response_headers)
        self.conn.send_data(stream_id, data, end_stream=True)
        self.transport.write(self.conn.data_to_send())
        
        print "Done in streamComplete."

    def db_open(self):
        db = MySQLdb.connect("localhost", "130user", "130security", "cs130")
        cursor = db.cursor()
        return (db, cursor)  

    def db_close(self, db):
        db.close()       

    def db_validate(self, data):
        db, cursor = self.db_open()

        cursor.execute(
            "SELECT username, COUNT(*) FROM Users WHERE username='%s' " % data
        )        

        has_it = cursor.fetchone()
        print "--> FETCHED: ", has_it[0]
        self.db_close(db)
        return has_it[0]
        
    # store values in database
    def db_set(self, dat, stream_id):
        db, cursor = self.db_open()
        
        print "in db_set, values %s %s %s" % (dat["username"], dat["email"], dat["token"])
        
        sql = "INSERT INTO Users (username, email, id_token) VALUES ('%s', '%s', '%s')" % \
             (dat["username"], dat["email"], dat["token"])
        
        try:
            cursor.execute(sql)
            db.commit()
            print "Values inserted into database."
        except:
            db.rollback()
            print "Error inserting, rolling back..."
            print "409 Conflict, Invalid POST -- entry already in database?"
            
        self.db_close(db)

    # store values in database
    def db_update(self, dat, stream_id):
        db, cursor = self.db_open()

        print "in db_set, values %s %s %s" % (dat["username"], dat["email"], dat["token"])
        
        sql = 'UPDATE Users SET id_token="%s" WHERE username="%s" ' % (dat["token"], dat["username"])
        
        print "UPDATING token"
        
        try:
            cursor.execute(sql)
            db.commit()
            print "New token value '%s' inserted into database." % dat["token"]
        except:
            db.rollback()
            print "Error inserting, rolling back..."
            print "409 Conflict, Invalid POST -- entry already in database?"
            
        self.db_close(db)

    # get values from database
    def db_get(self, data):
        
        print "in db_get with username '%s'" % data
            
        try:
            db, cursor = self.db_open()
            cursor.execute("SELECT id_token FROM Users WHERE username= %s ", (data,))
            res = cursor.fetchall()
            self.db_close(db)
        except:
            print "Error fetching data..."
        
        print "Values obtained from database, token = ", res[0][0]

        # Specify what to return for GET requests
        # in this case, return username and token for the user
        jstr = {}
        jstr['username'] = data
        jstr['token'] = res[0][0]
        jstr_data = json.dumps(jstr)
        return jstr_data

    def errorFound(self, stream_id):
        self.error = False
        self.return_XXX('404', stream_id)

    def return_200(self, to_send):
        """
        Pack and return 200 status.
        """
        response_headers = [
            (':status', '200'),
            ('content-type', 'application/json'),
            ('content-length', len(to_send)),
            ('server', 'TwoEfAy'),
        ]
        return response_headers

    def return_XXX(self, status, stream_id):    
        """
        Not found or error, return 404 status.
        Unsupported method, return 405 status.
        """
        response_headers = [
            (':status', status),
            ('content-length', '0'),
            ('server', 'TwoEfAy'),
        ]
        self.conn.send_headers(stream_id, response_headers, end_stream=True)

class H2Factory(Factory):
    def __init__(self, root):
        self.root = root

    def buildProtocol(self, addr):
        return H2Protocol(self.root)

root = sys.argv[1]

with open('../certs/server.crt', 'r') as f:
    cert_data = f.read()
with open('../certs/server.key', 'r') as f:
    key_data = f.read()

cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_data)
key = crypto.load_privatekey(crypto.FILETYPE_PEM, key_data)
options = ssl.CertificateOptions(
    privateKey=key,
    certificate=cert,
    acceptableProtocols=[b'h2'],
)

endpoint = endpoints.SSL4ServerEndpoint(reactor, 8080, options, backlog=128)
print "Server is running..."
endpoint.listen(H2Factory(root))
reactor.run()
