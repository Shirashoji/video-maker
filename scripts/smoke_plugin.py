"""Exercise the actual bundled launcher with an isolated workspace."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(plugin: Path, workspace: Path):
    config = json.loads((plugin / '.mcp.json').read_text())['mcpServers']['video-maker']
    params = StdioServerParameters(
        command=config['command'],
        args=[arg.replace('${CLAUDE_PLUGIN_ROOT}', str(plugin)) for arg in config['args']],
        env={**os.environ, 'VIDEO_MAKER_WORKSPACE': str(workspace)},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            tools = await client.list_tools()
            print(f'Tools: {len(tools.tools)}', flush=True)
            info = await client.call_tool('workspace_info', {})
            assert not info.isError
            saved = await client.call_tool('save_project', {
                'path': 'smoke.json', 'overwrite': True,
                'project': {'name': 'Packaged smoke test', 'width': 320, 'height': 240,
                            'scenes': [{'id': 'scene', 'duration': 1,
                                        'captions': [{'text': '接続テスト', 'start': 0.1, 'end': 0.9}]}]}})
            assert not saved.isError, saved
            job = await client.call_tool('render_preview', {'path': 'smoke.json'})
            assert not job.isError, job
            job_id = json.loads(job.content[0].text)['job_id']
            for _ in range(300):
                reply = await client.call_tool('job_status', {'job_id': job_id})
                state = json.loads(reply.content[0].text)
                if state['status'] in ('complete', 'failed'):
                    break
                await asyncio.sleep(0.2)
            assert state['status'] == 'complete', state
            # Exercise the visual MCP response as well as structured tool results.
            frames = await client.call_tool('inspect_frames', {'path': state['result']['video'], 'count': 3})
            assert not frames.isError and any(x.type == 'image' for x in frames.content), frames
            print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('plugin', type=Path)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(check(args.plugin.resolve(), args.workspace.resolve()))
