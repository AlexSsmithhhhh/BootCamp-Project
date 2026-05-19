import fs from 'node:fs/promises';
import path from 'node:path';

const token = process.env.DISCORD_TOKEN;
const channelId = process.env.LEADERBOARD_CHANNEL_ID || process.env.DISCORD_LEADERBOARD_CHANNEL_ID;
const configuredMessageId = (
  process.env.LEADERBOARD_MESSAGE_ID
  || process.env.DISCORD_LEADERBOARD_MESSAGE_ID
  || process.env.DASHBOARD_MESSAGE_ID
  || ''
).trim() || null;

if (!token || !channelId) {
  throw new Error('DISCORD_TOKEN and LEADERBOARD_CHANNEL_ID are required.');
}

const runningOnRailway = Boolean(process.env.RAILWAY_ENVIRONMENT);
const defaultDataDir = runningOnRailway
  ? (process.env.RAILWAY_VOLUME_MOUNT_PATH || '/app/data')
  : path.resolve('data');
const dataPath = process.env.LEADERBOARD_DATA_PATH
  || process.env.DISCORD_LEADERBOARD_DATA_PATH
  || path.join(defaultDataDir, 'discord-leaderboard.json');

const storedDashboard = await readStoredDashboard(dataPath);
const activeMessageId = configuredMessageId || storedDashboard?.messageId || null;
const activeSource = configuredMessageId ? 'env' : (storedDashboard?.messageId ? 'storage' : 'none');

console.log(`Dashboard channel: ${channelId}`);
console.log(`Configured message: ${configuredMessageId || '-'}`);
console.log(`Stored message: ${storedDashboard?.messageId || '-'}`);
console.log(`Active message: ${activeMessageId || '-'} (${activeSource})`);

if (activeMessageId) {
  const activeMessage = await fetchMessage(channelId, activeMessageId);
  if (activeMessage) {
    printMessage(activeMessage, 'ACTIVE');
  } else {
    console.log(`ACTIVE\t${activeMessageId}\tmessage_not_found`);
  }
}

const response = await fetch(`https://discord.com/api/v10/channels/${channelId}/messages?limit=10`, {
  headers: {
    Authorization: `Bot ${token}`,
  },
});

if (!response.ok) {
  throw new Error(`${response.status}: ${await response.text()}`);
}

const messages = await response.json();

for (const message of messages) {
  printMessage(message, message.id === activeMessageId ? 'ACTIVE' : 'recent');
}

async function readStoredDashboard(filePath) {
  try {
    const raw = await fs.readFile(filePath, 'utf8');
    return JSON.parse(raw).dashboard || null;
  } catch (error) {
    if (error.code === 'ENOENT') {
      return null;
    }
    throw error;
  }
}

async function fetchMessage(targetChannelId, messageId) {
  const messageResponse = await fetch(
    `https://discord.com/api/v10/channels/${targetChannelId}/messages/${messageId}`,
    {
      headers: {
        Authorization: `Bot ${token}`,
      },
    },
  );

  if (messageResponse.status === 404) {
    return null;
  }
  if (!messageResponse.ok) {
    throw new Error(`${messageResponse.status}: ${await messageResponse.text()}`);
  }
  return messageResponse.json();
}

function printMessage(message, marker) {
  const embedTitle = message.embeds?.[0]?.title ?? '';
  const updatedField = message.embeds?.[0]?.fields?.find((field) => field.name === 'Обновление')?.value ?? '';
  console.log([
    marker,
    message.id,
    message.author?.username,
    message.timestamp,
    embedTitle,
    updatedField.replace(/\s+/g, ' ').slice(0, 120),
    (message.content || '').slice(0, 60),
  ].join('\t'));
}
