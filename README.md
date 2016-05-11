# server

source [hyper-h2 demo](https://github.com/python-hyper/hyper-h2/blob/master/examples/twisted/twisted-server.py)

### Requirements
- python 2.7.9+
- pip
- h2
- twisted
- pyopenssl

Also may need to rebuild cURL with the nghttp2 to be able to send HTTP/2.0 requests.
If you need help, [click here for instructions](https://serversforhackers.com/video/curl-with-http2-support).
You may also look at hyper or httpie, httpie-http2.

To run server:
```sh
python twisted-server.py localhost
```

Sample GET:
```sh
curl --http2 https://httpbin.org/get
curl --http2 https://localhost:8080
```
Sample POST:
```sh
curl --http2 -H "Content-Type: application/json" -X POST -d '{"username":"poncho","token":"3498573984579348"}' https://localhost:8080/
```
