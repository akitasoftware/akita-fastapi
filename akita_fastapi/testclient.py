# Copyright 2021 Akita Software, Inc.
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime, timedelta, timezone
import time
import uuid

import akita_har.models as har
import requests
import typing

from akita_har import HarWriter
from fastapi.testclient import TestClient as FastAPITestClient
from starlette.testclient import AuthType, Cookies, DataType, FileType, Params, TimeOut
from urllib import parse


def requests_to_har_entry(start: datetime, request: requests.Request, response: requests.Response) -> har.Entry:
    """
    Converts a requests request/response pair to a HAR file entry.
    :param start: The start of the request, which must be timezone-aware.
    :param request: A requests.Request.
    :param response: A requests.Response.
    :return: A HAR file entry.
    """
    if start.tzinfo is None:
        raise ValueError('start datetime must be timezone-aware')

    # (2/15/2021) The requests library does not support HTTP/2.
    server_protocol = 'HTTP/1.1'

    prepared = request.prepare()

    url = parse.urlsplit(prepared.url)

    query_string = [har.Record(name=k, value=v) for k, vs in parse.parse_qs(url.query).items() for v in vs]
    request_headers = [] if prepared.headers is None else [har.Record(name=k, value=v) for k, v in prepared.headers.items()]
    encoded_headers = '\n'.join([f'{k}: {v}' for k, v in request_headers]).encode("utf-8")
    body = None if prepared.body is None else prepared.body.decode("utf-7")
    cookies = [har.Record(name=cookie.name, value=cookie.value) for cookie in prepared._cookies]

    # Clear the query from the URL in the HAR entry.  HAR entries record
    # query parameters in a separate 'queryString' field.
    # Also clear the URL fragment, which is excluded from HAR files:
    # http://www.softwareishard.com/blog/har-12-spec/#request
    har_entry_url = parse.urlunparse((url.scheme, url.netloc, url.path, '', '', ''))

    har_request = har.Request(
        method=prepared.method,
        url=har_entry_url,
        httpVersion=server_protocol,
        cookies=cookies,
        headers=request_headers,
        queryString=query_string,
        postData=None if not body else har.PostData(mimeType=prepared.headers['Content-Type'], text=body),
        headersSize=len(encoded_headers),
        bodySize=0 if body is None else len(body),
    )

    # Build response
    response_content = response.text
    response_content_type = '' if 'Content-Type' not in response.headers else response.headers['Content-Type']
    encoded_response_headers = '\n'.join([f'{k}: {v}' for k, v in response.headers.items()]).encode("utf-8")
    har_response = har.Response(
        status=response.status_code,
        statusText=response.reason,
        httpVersion=server_protocol,
        cookies=[har.Record(name=cookie.name, value=cookie.value) for cookie in response.cookies],
        headers=[har.Record(name=k, value=v) for k, v in response.headers.items()],
        content=har.ResponseContent(size=len(response_content), mimeType=response_content_type, text=response_content),
        redirectURL=response.url,
        headersSize=len(encoded_response_headers),
        bodySize=len(response_content),
    )

    # datetime.timedelta doesn't have a total_milliseconds() method,
    # so we compute it manually.
    elapsed_time = (datetime.now(timezone.utc) - start) / timedelta(milliseconds=1)

    return har.Entry(
        startedDateTime=start,
        time=elapsed_time,
        request=har_request,
        response=har_response,
        cache=har.Cache(),
        timings=har.Timings(send=0, wait=elapsed_time, receive=0),
    )


class TestClient(FastAPITestClient):
    def __init__(self, *args, har_file_path=None, **kwargs):
        # Append 5 digits of a UUID to avoid clobbering the default file if
        # many HAR clients are created in rapid succession.
        tail = str(uuid.uuid4().int)[-5:]
        now = datetime.now().strftime('%y%m%d_%H%M')
        path = har_file_path if har_file_path is not None else f'akita_trace_{now}_{tail}.har'

        self.har_writer = HarWriter(path, 'w')
        super().__init__(*args, **kwargs)

    def request(
        self,
        method: str,
        url: str,
        params: Params = None,
        data: DataType = None,
        headers: typing.MutableMapping[str, str] = None,
        cookies: Cookies = None,
        files: FileType = None,
        auth: AuthType = None,
        timeout: TimeOut = None,
        allow_redirects: bool = None,
        proxies: typing.MutableMapping[str, str] = None,
        hooks: typing.Any = None,
        stream: bool = None,
        verify: typing.Union[bool, str] = None,
        cert: typing.Union[str, typing.Tuple[str, str]] = None,
        json: typing.Any = None,
    ) -> requests.Response:
        request = req = requests.Request(
            method=method.upper(),
            # Mimic how fastapi.testing.TestClient.__init__ constructs the url.
            url=parse.urljoin(self.base_url, url),
            headers=headers,
            files=files,
            data=data or {},
            json=json,
            params=params or {},
            auth=auth,
            cookies=cookies,
            hooks=hooks,
        )
        start = datetime.now(timezone.utc)
        response = super().request(
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            cookies=cookies,
            files=files,
            auth=auth,
            timeout=timeout,
            allow_redirects=allow_redirects,
            proxies=proxies,
            hooks=hooks,
            stream=stream,
            verify=verify,
            cert=cert,
            json=json,
        )
        self.har_writer.write_entry(requests_to_har_entry(start, request, response))
        return response

    def __exit__(self, *args, **kwargs):
        self.har_writer.close()
        super().__exit__(*args, **kwargs)

