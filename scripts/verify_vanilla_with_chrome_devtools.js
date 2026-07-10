/**
 * 使用 Chrome DevTools MCP 验证 Vanilla 前端页面的辅助脚本。
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import fs from 'fs';
import path from 'path';

const OUTPUT_DIR = process.env.OUTPUT_DIR || '/tmp/verify-output';
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function main() {
  const targetUrl = process.env.TARGET_URL || 'http://localhost:8000/';
  const message = process.env.TEST_MESSAGE || '你好，请介绍一下自己';

  console.error(`[verify-vanilla] Connecting to Chrome DevTools MCP for ${targetUrl}`);

  const transport = new StdioClientTransport({
    command: 'npx',
    args: [
      'chrome-devtools-mcp@latest',
      '--headless',
      '--no-usage-statistics',
      '--no-performance-crux',
    ],
    env: {
      ...process.env,
    },
  });

  const client = new Client(
    { name: 'verify-vanilla-client', version: '1.0.0' },
    { capabilities: {} },
  );

  await client.connect(transport);
  console.error('[verify-vanilla] Connected');

  console.error(`[verify-vanilla] Navigating to ${targetUrl}`);
  await client.callTool({
    name: 'navigate_page',
    arguments: { url: targetUrl },
  });

  await sleep(3000);

  const screenshotPath = path.join(OUTPUT_DIR, 'vanilla-initial.png');
  console.error(`[verify-vanilla] Taking screenshot: ${screenshotPath}`);
  await client.callTool({
    name: 'take_screenshot',
    arguments: { filePath: screenshotPath },
  });

  const snapshotRes = await client.callTool({
    name: 'take_snapshot',
    arguments: {},
  });
  console.log(JSON.stringify({ step: 'snapshot-initial', result: snapshotRes.content }, null, 2));

  // Check elements and loaded agents
  const found = await evaluateJson(client, `
    const input = document.getElementById('message-input');
    const button = document.getElementById('send-btn');
    const agentSelect = document.getElementById('agent-select');
    const status = document.getElementById('status-indicator');
    return {
      inputFound: !!input,
      buttonFound: !!button,
      inputPlaceholder: input ? input.placeholder : null,
      buttonText: button ? button.textContent : null,
      buttonDisabled: button ? button.disabled : null,
      agentOptions: agentSelect ? Array.from(agentSelect.options).map(o => o.value) : [],
      statusText: status ? status.textContent : null,
      statusClass: status ? status.className : null,
    };
  `);
  console.log(JSON.stringify({ step: 'find-elements', result: found }, null, 2));

  if (found.inputFound && found.buttonFound) {
    console.error('[verify-vanilla] Filling input and sending message');
    await evaluateJson(client, `
      const input = document.getElementById('message-input');
      if (input) {
        input.value = ${JSON.stringify(message)};
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      return { valueSet: !!input };
    `);

    await evaluateJson(client, `
      const button = document.getElementById('send-btn');
      if (button && !button.disabled) {
        button.click();
        return { clicked: true };
      }
      return { clicked: false, disabled: button ? button.disabled : null };
    `);

    for (let i = 0; i < 6; i++) {
      await sleep(3000);
      const state = await evaluateJson(client, `
        const bubbles = Array.from(document.querySelectorAll('.message .bubble'))
          .map(el => el.textContent).filter(Boolean);
        const input = document.getElementById('message-input');
        const button = document.getElementById('send-btn');
        return {
          bubbleCount: bubbles.length,
          bubbles,
          inputValue: input ? input.value : null,
          buttonDisabled: button ? button.disabled : null,
        };
      `);
      console.log(JSON.stringify({ step: 'poll-state', iteration: i, result: state }, null, 2));
    }

    const chatScreenshotPath = path.join(OUTPUT_DIR, 'vanilla-after-send.png');
    console.error(`[verify-vanilla] Taking screenshot after send: ${chatScreenshotPath}`);
    await client.callTool({
      name: 'take_screenshot',
      arguments: { filePath: chatScreenshotPath },
    });

    const chatSnapshotRes = await client.callTool({
      name: 'take_snapshot',
      arguments: {},
    });
    console.log(JSON.stringify({ step: 'snapshot-after-send', result: chatSnapshotRes.content }, null, 2));
  } else {
    console.error('[verify-vanilla] Input or button not found');
  }

  await client.close();
  console.error('[verify-vanilla] Done');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractJsonFromEval(text) {
  const match = text.match(/```json\n([\s\S]*?)\n```/);
  if (match) {
    return JSON.parse(match[1]);
  }
  const trimmed = text.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    return JSON.parse(trimmed);
  }
  throw new Error(`Cannot extract JSON from: ${text}`);
}

async function evaluateJson(client, code) {
  const res = await client.callTool({
    name: 'evaluate_script',
    arguments: {
      function: `() => { ${code} }`,
    },
  });
  const text = res.content[0].text;
  return extractJsonFromEval(text);
}

main().catch((err) => {
  console.error('[verify-vanilla] Error:', err);
  process.exit(1);
});
