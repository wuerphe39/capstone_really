import asyncio
import json
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from .settings import ROOT, settings


async def retrieve_outing_facts(pet_id, outing_id, question):
    env = dict(os.environ)
    env['PETMIND_DATABASE_URL'] = settings.database_url
    parameters = StdioServerParameters(command=sys.executable,
        args=['-m', 'petmind.backend.mcp_server'], cwd=str(ROOT), env=env)
    async with asyncio.timeout(30):
        async with Client(parameters, read_timeout_seconds=25) as client:
            result = await client.call_tool('get_outing_facts',
                {'pet_id': pet_id, 'outing_id': outing_id, 'question': question})
            if result.is_error:
                raise RuntimeError('outing MCP retrieval failed')
            payload = result.structured_content
            if payload is None:
                payload = json.loads(''.join(item.text for item in result.content if item.type == 'text'))
            if not isinstance(payload, dict) or not isinstance(payload.get('facts'), list):
                raise ValueError('invalid outing facts')
            return payload


async def retrieve_records(pet_id, before, query, days=7, start=None, semantic=False):
    env = dict(os.environ)
    env['PETMIND_DATABASE_URL'] = settings.database_url
    parameters = StdioServerParameters(command=sys.executable,
                                       args=['-m', 'petmind.backend.mcp_server'],
                                       cwd=str(ROOT), env=env)
    async with asyncio.timeout(45):
        async with Client(parameters, read_timeout_seconds=35) as client:
            outputs, calls = {}, []
            for name, args, key in [
                ('search_observations', {'pet_id': pet_id, 'before': before, 'query': query,
                                         'days': days, 'start': start, 'semantic': semantic}, 'search'),
                ('get_observation_stats', {'pet_id': pet_id, 'before': before, 'days': days, 'start': start}, 'stats'),
                ('get_care_history', {'pet_id': pet_id, 'before': before, 'start': start}, 'care')
            ]:
                result = await client.call_tool(name, args)
                if result.is_error:
                    raise RuntimeError(f'MCP tool failed: {name}')
                payload = result.structured_content
                if payload is None:
                    payload = json.loads(''.join(item.text for item in result.content if item.type == 'text'))
                if not isinstance(payload, dict):
                    raise ValueError(f'MCP tool returned invalid data: {name}')
                outputs[key] = payload
                calls.append({'tool': name, 'status': 'ok'})
    return {'mode': 'mcp', 'status': 'ok', 'records': outputs['search']['records'],
            'search': outputs['search']['search'],
            'stats': outputs['stats'], 'care_history': outputs['care']['history'], 'tool_calls': calls}
