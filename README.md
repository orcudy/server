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

Running Twisted for a good time:
```
twistd -n web --path . --https=8081 --privkey <your key here> --certificate <your certificate here>
```

### If deploying locally
Sample GET:
```sh
curl --http2 https://httpbin.org/get
curl --http2 https://localhost:8080
```
Sample POST:
```sh
curl --http2 -H "Content-Type: application/json" -X POST -d '{"username":"poncho","email":"whatever@some.com","token":"3498573984579348"}' https://localhost:8080/
```

### Deployed on the droplet

POST:
```sh
curl --http2 -H "Content-Type: application/json" -X POST -d '{"username":"sexy","email":"sexy@email.com","token":"3498573984579348"}' https://45.55.160.135:8080/register
```

GET:
```sh
curl --http2 https://45.55.160.135:8080/read/sexy
```