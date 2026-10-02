"""Verify release credentials without admitting an operation or changing runtime."""
import json
import os
import urllib.error
import urllib.request

from release_client import NoRedirect, endpoint

APP = 'securo-production'
OTHER = 'securo-ci-test'


def verify(call):
    status, before = call('read', 'GET', APP)
    if status != 200 or not isinstance(before.get('operations'), list):
        raise ValueError('Production read access failed')
    for token, method, app in (('invalid', 'GET', APP), ('deploy', 'GET', APP),
                               ('read', 'POST', APP), ('read', 'GET', OTHER),
                               ('deploy', 'GET', OTHER)):
        if call(token, method, app)[0] != 401:
            raise ValueError('Release credential boundary failed')
    # Empty input is rejected by the HTTP router before Gate.release is called.
    status, result = call('deploy', 'POST', APP)
    if status != 400 or result != {'error': 'Unknown mutation'}:
        raise ValueError('Production deploy authentication or input boundary failed')
    status, after = call('read', 'GET', APP)
    if status != 200 or after != before:
        raise ValueError('Access verification changed or raced release history')
    return {'release_access_verified': True, 'app': APP, 'release_history_unchanged': True,
            'no_operation_admitted': True, 'other_app_denied': True}


def main():
    origin = endpoint(os.environ['RELEASE_ORIGIN'])
    tokens = {'read': os.environ['RELEASE_READ_TOKEN'], 'deploy': os.environ['RELEASE_DEPLOY_TOKEN'],
              'invalid': 'invalid-credential-for-access-verification'}
    if min(len(tokens['read']), len(tokens['deploy'])) < 32 or tokens['read'] == tokens['deploy']:
        raise ValueError('Select separate bounded release credentials')
    opener = urllib.request.build_opener(NoRedirect())

    def call(token, method, app):
        request = urllib.request.Request(origin + '/v1/apps/' + app + '/operations',
            method=method, data=b'{}' if method == 'POST' else None,
            headers={'Authorization': 'Bearer ' + tokens[token], 'Content-Type': 'application/json'})
        try:
            response = opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(65537)
            if len(raw) > 65536: raise ValueError('Oversized release access response')
            return response.code, json.loads(raw)

    print(json.dumps(verify(call)))


if __name__ == '__main__': main()
