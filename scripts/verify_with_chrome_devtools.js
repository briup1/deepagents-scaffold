/**
 * 使用 Chrome DevTools MCP 验证前端页面的辅助脚本。
 * 通过 stdio 启动 npx chrome-devtools-mcp@latest，然后执行指定的工具序列。
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import fs from 'fs';
import path from 'path';

const OUTPUT_DIR = process.env.OUTPUT_DIR || '/tmp/verify-output';
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function main() {
  const targetUrl = process.env.TARGET_URL || 'http://localhost:3000';
  const message = process.env.TEST_MESSAGE || '你好，请介绍一下自己';

  console.error(`[verify] Connecting to Chrome DevTools MCP for ${targetUrl}`);

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
    { name: 'verify-client', version: '1.0.0' },
    { capabilities: {} },
  );

  await client.connect(transport);
  console.error('[verify] Connected');

  // 1. 导航到目标页面
  console.error(`[verify] Navigating to ${targetUrl}`);
  await client.callTool({
    name: 'navigate_page',
    arguments: { url: targetUrl },
  });

  // 2. 等待页面稳定
  await sleep(2000);

  // 3. 截图保存
  const screenshotPath = path.join(OUTPUT_DIR, 'react-initial.png');
  console.error(`[verify] Taking screenshot: ${screenshotPath}`);
  await client.callTool({
    name: 'take_screenshot',
    arguments: { filePath: screenshotPath },
  });

  // 4. 获取页面快照
  console.error('[verify] Taking snapshot');
  const snapshotRes = await client.callTool({
    name: 'take_snapshot',
    arguments: {},
  });
  console.log(JSON.stringify({ step: 'snapshot-initial', result: snapshotRes.content }, null, 2));

  // 5. 检查 API 数据是否加载（agents / tools）
  console.error('[verify] Checking loaded data');
  const dataCheck = await evaluateJson(client, `
    return Promise.all([
      fetch('/api/agents/').then(r => r.json()).catch(e => ({ error: e.message })),
      fetch('/api/tools/').then(r => r.json()).catch(e => ({ error: e.message })),
    ]).then(([agents, tools]) => ({ agents, tools }));
  `);
  console.log(JSON.stringify({ step: 'api-data-check', result: dataCheck }, null, 2));

  // 6. 查找输入框和发送按钮
  console.error('[verify] Finding input and send button');
  const found = await evaluateJson(client, `
    const input = document.querySelector('input[type="text"]');
    const button = document.querySelector('button[type="submit"]');
    return {
      inputFound: !!input,
      buttonFound: !!button,
      inputPlaceholder: input ? input.placeholder : null,
      buttonText: button ? button.textContent : null,
      buttonDisabled: button ? button.disabled : null,
    };
  `);
  console.log(JSON.stringify({ step: 'find-elements', result: found }, null, 2));

  // 7. 收集浏览器 console 消息
  await sleep(500);
  const consoleRes = await client.callTool({
    name: 'list_console_messages',
    arguments: {},
  });
  console.log(JSON.stringify({ step: 'console-messages', result: consoleRes.content }, null, 2));

  // 8. 如果找到输入框，发送测试消息
  if (found.inputFound && found.buttonFound) {
    console.error('[verify] Filling input and sending message');
    // 通过 evaluate_script 设置值并触发 React onChange（onInput）事件
    await evaluateJson(client, `
      const input = document.querySelector('input[type="text"]');
      if (input) {
        const value = ${JSON.stringify(message)};
        // 使用原生 setter 绕过 React 受控组件限制
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      return { valueSet: !!input };
    `);

    // 检查按钮是否已启用
    const afterType = await evaluateJson(client, `
      const input = document.querySelector('input[type="text"]');
      const button = document.querySelector('button[type="submit"]');
      return {
        inputValue: input ? input.value : null,
        buttonDisabled: button ? button.disabled : null,
      };
    `);
    console.log(JSON.stringify({ step: 'after-type', result: afterType }, null, 2));

    if (!afterType.buttonDisabled) {
      console.error('[verify] Submitting form directly');
      await evaluateJson(client, `
        const form = document.querySelector('form');
        if (form) {
          form.requestSubmit();
          return { submitted: true };
        }
        return { submitted: false };
      `);

      // 多次检查状态，等待流式回复
      for (let i = 0; i < 6; i++) {
        await sleep(3000);
        const state = await evaluateJson(client, `
          const bubbles = Array.from(document.querySelectorAll('.whitespace-pre-wrap'))
            .map(el => el.textContent).filter(Boolean).slice(0, 20);
          const thinkingEl = Array.from(document.querySelectorAll('*')).find(el => el.textContent === 'Thinking...');
          const input = document.querySelector('input[type="text"]');
          return { bubbleCount: bubbles.length, bubbles, thinking: !!thinkingEl, inputValue: input ? input.value : null };
        `);
        console.log(JSON.stringify({ step: 'poll-state', iteration: i, result: state }, null, 2));
      }
    } else {
      console.error('[verify] Button still disabled after typing');
    }

    const chatScreenshotPath = path.join(OUTPUT_DIR, 'react-after-send.png');
    console.error(`[verify] Taking screenshot after send: ${chatScreenshotPath}`);
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
    console.error('[verify] Input or button not found');
  }

  await client.close();
  console.error('[verify] Done');
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
  console.error('[verify] Error:', err);
  process.exit(1);
});
