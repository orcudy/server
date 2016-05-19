# Server

This server is based on the Twisted Python example from [hyper-h2 demo](https://github.com/python-hyper/hyper-h2/blob/master/examples/twisted/twisted-server.py)

### Pre-requisites: 
- python 2.7.9+
- pip
- mysql-server
- virtualenv (optional, but highly recommended!)

##### Note: 
Some of the Requirements listed below may need other libraries to be installed, otherwise you'll 
have issues when you try to install libraries with pip. 
Off the top of my head, you may need to run
```sh
sudo apt-get install python-cffi libffi-dev build-essentials python-dev libmysqlclient-dev
```

### Requirements
  * h2
  * hyper
  * twisted
  * cffi
  * cryptography
  * service_identity
  * pyopenssl
  * typing
  * setuptools
  * pyasnl
  * pyasnl-modules
  * mysql-python
  * pycrypto
  * python-dateutil

For example, to install the above in your virtualenv run:
```sh
pip install h2 twisted cryptography mysql-python etc...
```

#### Optional (helpful for testing)
- httpie
- httpie-http2

###### NOTE on testing with cURL
You may also need to rebuild cURL with the nghttp2 to be able to send HTTP/2.0 requests.
If you need help, [click here for instructions](https://serversforhackers.com/video/curl-with-http2-support).
You may also want to look at hyper or httpie, httpie-http2 as additional testing tools to cURL.

#### Keys & certificates
You will have to generate your own certificate and key as they are required for HTTP/2.0, so
lookup a tutorial on how to do that if you don't know. You'll see in the code, near the bottom,
where to specify the location of your certificate and key. If you don't do this, the server won't run.

#### To run server:
```sh
python twisted-server.py localhost
```
You will have to enter your PEM key phrase after running the above command.

#### Running Twisted for a good time:
```
twistd -n web --path . --https=8081 --privkey <your key here> --certificate <your certificate here>
```

#### If deploying locally
Test whether you successfully rebuilt cURL with the following GET:
```sh
curl --http2 https://httpbin.org/get
```

> Assuming you've set up your database correctly, created the desired table 
> within your database, and provided the correct database info and credentials 
> in the **db_set** and **db_get** functions, you'll be able to register a user
> **sexy** via a POST with the following request:
```sh
curl --http2 -H "Content-Type: application/json" -X POST -d '{"username":"sexy","email":"whatever@some.com","token":"3498573984579348"}' https://localhost:8080/register/<encrypted string>
```

### GET request to your server:
```sh
curl --http2 https://localhost:8080/user/sexy
```
> Note: in the above GET request, we try to obtain info on a user **sexy**. 
> Of course, this user > has to be in your database before you can get a return
> for this.

### Deployed on the droplet
The database has been setup on Chris's droplet, so you can test POST and GET 
requests in the following way:

#### POST:
```sh
curl --http2 -H "Content-Type: application/json" -X POST -d '{"username":"sexy","email":"sexy@email.com","token":"3498573984579348"}' https://45.55.160.135:8080/register/<encrypted string>
```
###### POST params available and their purpose:
| Path        | Purpose                   | JSON data sent with request         |
| ----------- |:-------------------------:|------------------------------------:|
| /register   | register new user         | username, email, token (empty)      |
| /update     | update user token         | username, token (non-empty)         |
| /login      | user attempted login      | username                            |
| /success    | successful login          | username, login state (success)     |
| /failure    | failed login              | username, login state (failure)     |


#### GET:
```sh
curl --http2 https://45.55.160.135:8080/user/sexy/<encrypted string>
```

The above get should return a JSON of the form
```
{"usernae": "sexy", "token":"3498573984579348"}
```

#### Note on _encrypted string_:
The **crypto.py** module does the encryption and decryption. I call it within
the server to decrypt the encrypted string sent with the request but if you,
like me, test with cURL, you'll have to manually generate the encrypted string
as follows.
  * Open up your text editor and save the following in a generator.py (or whatever).
```python
import crypt
from datetime import datetime
from dateuril.parser import parse

# this is my super-secret key
do_crypto = crypt.AEScipher('f456a56b567f4094ccd45745f063a465')
date = datetime.now()
date_format = '%Y/%m/%d %H:%M:%S'

secret = str(date)
msg = do_crypto.encrypt(secret)
print msg
```
Run it and you'll get the string. :)

#### How to run server in the background:
Since the server requires the PEM pass phrase to be provided when starting it, 
it is not feasible to just run it with nohup. Instead, here is how I've been 
running it in background:

* Start the server as usual and type in the pass phrase when prompted.
  ```sh
  python twisted-server.py localhost
  ```
* Pause the server with "Ctrl-z," which will print something like
  ```sh
  [1]+ Stopped        python twisted-server.py 45.55.160.135
  ```
* Note that [1] is the job ID that we now use to disown the service:
  ```sh
  disown -h %1
  ```
* Now start the job in background:
  ```sh 
  bg %1
  ```
* **PROFIT!**