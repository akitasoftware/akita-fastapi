# Akita FastAPI Integration

This package extends `fastapi.testclient.TestClient` in order to instrument
FastAPI integration tests, capturing requests and responses to the service
under test.  You can drop in `akita_fastapi.testclient.HarClient` everywhere you use
FastAPI's `TestClient`, and Akita will use your integration tests to build a
spec for your service.

Why build specs?  A spec shows your service's APIs.  Using Akita to build specs
from your integration tests makes it clear what APIs your code implements --
and you can diff specs, showing what impact a code change will have on your
customers.  For more info, see [Catching Breaking Changes
Faster](https://docs.akita.software/docs) in the Akita docs.

## See it in Action

Take a look at the [Akibox FastAPI
Tutorial](https://github.com/akitasoftware/akibox-tutorial), which
implements a toy Dropbox-like file server and tests it using the Akita FastAPI
Integration.
