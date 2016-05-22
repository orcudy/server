# TwoEfAy HTTP/2.0 Server

This server is based on the Twisted Python example from [hyper-h2 demo](https://github.com/python-hyper/hyper-h2/blob/master/examples/twisted/twisted-server.py)

### Pre-requisites: 
- python 2.7.9+
- pip
- mysql-server
- virtualenv (optional, but highly recommended!)

##### Note: 
Some of the Requirements listed below may need other libraries to be installed, otherwise you'll 
have issues when you try to install libraries with pip. 
Off the top of my head, you may need to run:
```sh
sudo apt-get install python-cffi libffi-dev build-essentials python-dev libmysqlclient-dev ...
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

***
#### NOTE on testing with cURL
You may also need to rebuild cURL with the nghttp2 to be able to send HTTP/2.0 
requests.
If you need help, [click here for instructions](https://serversforhackers.com/video/curl-with-http2-support).
You may also want to look at hyper or httpie, httpie-http2 as additional 
testing tools to cURL.

Test whether you successfully rebuilt cURL with the following GET and POST:
```sh
curl --http2 https://httpbin.org/get
curl --http2 -d {"hello":"world"} -X POST https://httpbin.org/post
```
Testing with httpbin.org is awesome because it returns the contents of your request
so you can see immediately if you sent over what you thought you did.
***

#### Keys & certificates
You will have to generate your own self-signed certificate and key as they are 
required for HTTP/2.0, so lookup a tutorial on how to do that if you don't know. 
You'll see in the code, at the bottom, where to specify the location of your 
certificate and key (mine are in a certs dir: "../certs/server.key")
If you don't do this, the server won't run (not properly, at least). You *may* 
create a key without a pass phrase for your own testing but this is clearly not 
a secure option in real life.


#### NOTE on MySQL databases
For the server to work properly, it is assumed you have previously set up a MySQL
database. If you don't know how to do that, here's a quick and dirty intro to
what I did:

```sh
sudo apt-get install mysql-server
```
During the install you'll be asked to set a root password. **Do NOT forget it.**

Start it: 
```sh 
mysql -u root -p 
<when prompted, enter the root password you set up>
```

```mysql
CREATE DATABASE cs130;
GRANT ALL ON cs130.* TO '130user' IDENTIFIED BY '130security';

USE cs130;
CREATE TABLE Users(
	username VARCHAR(40) UNIQUE NOT NULL PRIMARY KEY, 
	email VARCHAR(40) UNIQUE NOT NULL, 
	id_token VARCHAR(80) PRIMARY KEY, 
	dev_token VARCHAR(80)
); 

```
Note that *​*username**​ and *​*id_token**​ are the PRIMARY KEYS.
Also note that *​*username**​ and *​*email**​ are ​__UNIQUE__​ and ​__NOT NULL__​, 
(i.e. we can't create users with the same username or email **and** 
we can't create users with blank username or email).


Now, if you want to see what your table looks like, you run a query:
```mysql
SELECT * FROM Users;
```

On the droplet server this will return something like this:
```mysql
mysql> select * from Users;
+-----------+--------------------+----------------------+-----------+
| username  | email              | id_token             | dev_token |
+-----------+--------------------+----------------------+-----------+
| bro       | bro@email.com      | 76545246587232       | NULL      |
| isThisOn? | blsssa@example.com | 3IYsBH6wDEyVCZfn     | NULL      |
| sexy      | sexy@email.com     | 23472                | NULL      |
| something | bla@example.com    | 234h38fKW0dje238E    | NULL      |
| tester    | tester@email.com   | 4535343              | NULL      |
| testuser  | test@email.com     | 23598745434943758438 | NULL      |
+-----------+--------------------+----------------------+-----------+
```
The id_token here isn't very random/unique because these users were
created with an older version of the server. Also, the dev_token
is NULL because I created the column after the table already existed
and we haven't yet obtained the device tokens for these
users from their iPhones with the /verify POST request from the App.

You can run much more complex queries, of course. 
For example in the server I verify a certain user exists with the
following query:
```mysql
SELECT username, COUNT(*) FROM Users WHERE username='<username>'
```

I register new users into the database with the following:
```mysql
INSERT INTO Users (username, email, id_token, dev_token) VALUES ('<username>', '<email>', '<random token>', '');
```

---

#### To run server:
```sh
python twisted-server.py localhost
```
You will have to enter your PEM key phrase after running the above command.


#### If deploying locally

> Assuming you've set up your database correctly, created the desired table 
> within your database, and provided the correct database info and credentials 
> in the **db_open()** function, you'll be able to /register a user **sexy** via
> a POST with the following request:

```sh
curl --http2 -H "Content-Type: application/json" -X POST -d '{"username":"sexy","email":"whatever@some.com"}' https://localhost:8080/register
```

**NOTE:** 
If you get a error stating the certificate is self-signed and cannot be verified, then run cURL with the **-k** flag. 
For example, to register user **dude** with email **anial@email.com** and IGNORE certificate security:
```sh
curl --http2 -k -H "Content-Type: application/json" -X POST -d '{"username":"dude", "email":"animal@email.com"}' https://localhost:8080/register
```

### GET request to your server:
```sh
curl --http2 -k https://localhost:8080/user/sexy
```
> Note: in the above GET request, we try to obtain info on a user **sexy**. 
> Of course, this user has to be in your database before you can get a return
> for this.

===

### Deployed on the droplet
---
###### POST params available and their purpose:
| Path        | Purpose                                        | JSON data sent with request   | Server reaction                                          |
| ----------- |:----------------------------------------------:|------------------------------:|---------------------------------------------------------:|
| /register   | Client registers new user                      | username, email               | POSTs /register to Client with JSON with id_token        |
| /verify     | App verifies user + token device token         | id_token, dev_token           | Can now POST to APN with dev_token                       |
| /login      | Client reports that user attempts to log in    | id_token                      | POSTs to APN with dev_token                              |
| /success    | App reports user authenticated successfully    | id_token                      | POSTs /login to Client with JSON with id_token, success  |
| /failure    | App reports user authenticated unsuccessfully  | id_token                      | POSTS /login to Client with JSON with id_token, failure  |


The database has been setup on Chris's droplet, so you can test POST and GET 
requests in the following way:

#### Client -> Server /register POST:
```sh
curl --http2 -kv -H "Content-Type: application/json" -X POST -d '{"username":"crazy","email":"crazy@email.com"}' https://45.55.160.135:8080/register
```

#### GET:
```sh
curl --http2 -kv https://45.55.160.135:8080/user/crazy
```

The above get should return a JSON of the form
```
{"username": "crazy", "token":"<some token>"}
```

#### App -> Server /verify POST:
```sh
curl --http2 -k -H "Content-Type: application/json" -X POST -d '{"id_token":"3IYsBH6wDEyVCZfn","dev_token":"34f4rhg5424h234f83hf"}' https://localhost:8080/verify
```
This will set the dev_token for user identified by id_token who happens to currently be user "**isThisOn?**".

### Client -> Server /login POST:
```sh
curl --http2 -k -H "Content-Type: application/json" -X POST -d '{"token":"3IYsBH6wDEyVCZfn"}' https://localhost:8080/login
```

### App -> Server /success and /failure POSTs:
```sh
curl --http2 -k -H "Content-Type: application/json" -X POST -d '{"token":"3IYsBH6wDEyVCZfn"}' https://localhost:8080/success
curl --http2 -k -H "Content-Type: application/json" -X POST -d '{"token":"3IYsBH6wDEyVCZfn"}' https://localhost:8080/failure
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

**Currently, this functionality is disabled, so you don't have to generate
this string when testing!**

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