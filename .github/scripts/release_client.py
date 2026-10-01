"""Request a named private release; reconcile lost responses without shell access."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

TERMINAL = {'completed', 'rejected', 'failed', 'cancelled', 'needs_recovery', 'recovered'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None  # Never forward deployment/GitHub credentials to another URL.


def publication_identity(run, request):
    if (run.get('head_repository', {}).get('full_name') != 'Jascuas/securo'
            or run.get('head_branch') != 'codex/tensor' or run.get('head_sha') != request['source_sha']
            or run.get('path') != '.github/workflows/fork-release.yml'
            or run.get('event') != 'workflow_dispatch' or run.get('run_attempt') != request['build_run_attempt']):
        raise ValueError('Publication identity mismatch')
    if run.get('status') == 'completed':
        if run.get('conclusion') != 'success':
            raise ValueError('Publication did not complete successfully')
        return True
    return False


def wait_for_publication(request, token):
    # Dispatch is the publication's last job; it must finish before server admission.
    for _ in range(60):
        req = urllib.request.Request('https://api.github.com/repos/Jascuas/securo/actions/runs/' + str(request['build_run_id']),
                                     headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                                              'User-Agent': 'securo-isolated-release'})
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(131073)
            if len(raw) > 131072:
                raise ValueError('Oversized publication identity')
            run = json.loads(raw)
        if publication_identity(run, request):
            return
        time.sleep(2)
    raise ValueError('Publication completion pending; no deployment requested')


def endpoint(value):
    parsed = urllib.parse.urlparse(value)
    if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.ts.net')
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise ValueError('Select the private HTTPS service origin')
    return value.rstrip('/')


class Transport:
    def __init__(self, origin, app, deploy_token, read_token, github_token):
        self.url = endpoint(origin) + '/v1/apps/' + app + '/operations'
        self.deploy_token = deploy_token
        self.read_token = read_token
        self.github_token = github_token

    def call(self, method, operation=None, body=None):
        url = self.url + ('/' + operation if operation else '')
        token = self.read_token if method == 'GET' else self.deploy_token
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        if method == 'POST':
            headers['X-GitHub-Token'] = self.github_token
        request = urllib.request.Request(url, headers=headers, method=method,
                                         data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
                result = response.read(65537)
                if len(result) > 65536:
                    raise ValueError('Oversized release receipt')
                return response.status, json.loads(result)
        except urllib.error.HTTPError as error:
            if error.code not in (404, 409):
                raise ValueError('Release request rejected (HTTP ' + str(error.code) + ')') from None
            return error.code, json.loads(error.read(65536))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            return 0, {}  # The operation may have started; reconcile its fixed ID.


def release(request, transport, sleep=time.sleep, clock=time.monotonic, limit=600):
    deadline = clock() + limit
    submitted = False
    while clock() < deadline:
        status, receipt = transport.call('GET', request['operation_id']) if submitted else transport.call('POST', body=request)
        submitted = True
        if receipt.get('status') in TERMINAL:
            # Reject a confused or mismatched response before reporting success.
            if any(receipt.get(key) != value for key, value in request.items()):
                raise ValueError('Release receipt identity mismatch')
            return receipt
        if status == 404:
            submitted = False  # Same ID/content retry is server-idempotent.
        sleep(2)
    raise ValueError('Release result pending; reconcile the same operation ID on the server')


def main():
    app = 'securo-ci-test'
    sha = os.environ['SOURCE_SHA']
    config = os.environ['CONFIG_SHA256']
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not re.fullmatch(r'[0-9a-f]{64}', config):
        raise ValueError('Select the reviewed source and server configuration')
    build = int(os.environ['BUILD_RUN_ID'])
    attempt = int(os.environ['BUILD_RUN_ATTEMPT'])
    if not 0 < build < 2**63 or not 0 < attempt < 2**63:
        raise ValueError('Select a valid publication identity')
    request = {'app': app, 'operation_id': f'github-{build}-{attempt}', 'source_sha': sha,
               'build_run_id': build, 'build_run_attempt': attempt, 'config_sha256': config}
    wait_for_publication(request, os.environ['GITHUB_READ_TOKEN'])
    transport = Transport(os.environ['RELEASE_ORIGIN'], app, os.environ['RELEASE_DEPLOY_TOKEN'],
                          os.environ['RELEASE_READ_TOKEN'], os.environ['GITHUB_READ_TOKEN'])
    receipt = release(request, transport)
    safe = {key: receipt[key] for key in ('app', 'operation_id', 'status', 'source_sha', 'build_run_id', 'build_run_attempt')}
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
        output.write('## Isolated application release\n\n```json\n' + json.dumps(safe, indent=2) + '\n```\n')
    print(json.dumps(safe))
    if receipt['status'] != 'completed':
        raise SystemExit('The server did not verify release completion')


if __name__ == '__main__':
    main()
