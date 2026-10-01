"""Verify actual policy drops; a closed port is not an access-denial proof."""
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
import socket


def targets(value):
    entries = json.loads(value)
    if not isinstance(entries, list) or not 7 <= len(entries) <= 20:
        raise ValueError('Select the reviewed private denial targets')
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'host', 'port'} or type(entry['port']) is not int or not 0 < entry['port'] < 65536:
            raise ValueError('Invalid private denial target')
        address = ipaddress.ip_address(entry['host'])
        if address not in ipaddress.ip_network('100.64.0.0/10'):
            raise ValueError('Only private tailnet denial targets')
    return entries


def denied(entry, connect=socket.create_connection):
    try:
        with connect((entry['host'], entry['port']), timeout=2):
            raise ValueError('CI can reach a forbidden private service')
    except TimeoutError:
        return True
    except OSError:
        raise ValueError('Closed or unresolved service is not policy-denial evidence') from None


if __name__ == '__main__':
    entries = targets(os.environ['DENIED_ENDPOINTS'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(denied, entries))
    print(json.dumps({'private_network_denial_verified': True, 'target_count': len(entries)}))
