import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

loadLocalEnv();

const token = process.env.DISCORD_TOKEN;
let guildId = process.env.DISCORD_GUILD_ID;

if (!token) {
  throw new Error('DISCORD_TOKEN is required.');
}

const channelId = optionalString(
  'START_HERE_CHANNEL_ID',
  'REACTION_ROLE_CHANNEL_ID',
) ?? optionalFirstCsvString('REACTION_ROLE_CHANNEL_IDS');
const channelNames = optionalCsvArray('START_HERE_CHANNEL_NAMES', [
  'start-here',
  'start_here',
  'start here',
  'старт',
]);
const anchorMessageId = optionalString('START_HERE_ANCHOR_MESSAGE_ID');
const anchorAuthorNames = optionalCsvArray('START_HERE_ANCHOR_AUTHOR_NAMES', [
  'smith',
  'смит',
  'alexssmithhhhh',
]);
const dryRun = optionalBoolean('START_HERE_DRY_RUN', false);

const forexEmoji = String.fromCodePoint(0x2197, 0xfe0f);
const cryptoEmoji = String.fromCodePoint(0x1f4c8);

const promptEmbed = {
  color: 0x2ecc71,
  title: 'Что нужно сделать сейчас',
  description: [
    'Выбери одно или два направления, нажав на эмодзи под этим сообщением.',
    'После выбора бот выдаст роль Trader и роль выбранного направления.',
    '',
    `${forexEmoji} — Forex`,
    `${cryptoEmoji} — Crypto`,
    '',
    'Выбор ролей используется только для навигации и первичной сегментации участников. При необходимости направления можно изменить позже.',
    '',
    '🔒 Доступ к серверу откроется 1 июня 🚀',
  ].join('\n'),
};

const reactionEmojis = [forexEmoji, cryptoEmoji];

const botUser = await discordRequest('GET', '/users/@me');
guildId = guildId || await inferGuildId();
const channel = await findStartHereChannel();
const messages = await discordRequest(
  'GET',
  `/channels/${channel.id}/messages?limit=100`,
);
const anchor = await findAnchorMessage(channel, messages);
const oldPromptMessages = messages.filter((message) => (
  message.author?.id === botUser.id && isStartHerePrompt(message)
));
const newerMessagesAfterAnchor = anchor
  ? messages.filter((message) => (
    isAfter(message.id, anchor.id)
      && !oldPromptMessages.some((oldMessage) => oldMessage.id === message.id)
  ))
  : [];

console.log(`Start here channel: ${channel.name} (${channel.id})`);
console.log(`Anchor message: ${anchor ? `${anchor.id} by ${authorLabel(anchor.author)}` : 'not found'}`);
console.log(`Old bot prompt messages: ${oldPromptMessages.length}`);
if (newerMessagesAfterAnchor.length > 0) {
  console.log(
    `Notice: ${newerMessagesAfterAnchor.length} non-prompt message(s) are already below the anchor. ` +
      'Discord cannot insert a message in the middle; the new prompt will be posted at the bottom.',
  );
}

if (dryRun) {
  console.log('Dry run enabled; no Discord messages were changed.');
  process.exit(0);
}

for (const message of oldPromptMessages) {
  await discordRequest(
    'DELETE',
    `/channels/${channel.id}/messages/${message.id}`,
    null,
    [204, 404],
  );
  console.log(`Deleted old bot prompt: ${message.id}`);
}

const created = await discordRequest(
  'POST',
  `/channels/${channel.id}/messages`,
  {
    embeds: [promptEmbed],
    allowed_mentions: { parse: [] },
  },
);

for (const emoji of reactionEmojis) {
  await discordRequest(
    'PUT',
    `/channels/${channel.id}/messages/${created.id}/reactions/${encodeURIComponent(emoji)}/@me`,
    null,
    [204],
  );
}

console.log(`Created start-here prompt: ${created.id}`);
console.log(`Added reactions: ${reactionEmojis.join(' ')}`);
console.log(
  'If REACTION_ROLE_MESSAGE_IDS is set in Railway, update it to this new message ID or remove it so channel-based reaction roles work.',
);

async function findStartHereChannel() {
  if (channelId) {
    const fetchedChannel = await discordRequest('GET', `/channels/${channelId}`);
    return fetchedChannel;
  }

  const channels = await discordRequest('GET', `/guilds/${guildId}/channels`);
  const normalizedChannelNames = channelNames.map(normalizeName).filter(Boolean);
  const found = channels.find((item) => (
    item.name
      && [0, 5, 15, 16].includes(item.type)
      && normalizedChannelNames.includes(normalizeName(item.name))
  ));

  if (!found) {
    throw new Error(
      `Start-here channel not found. Set START_HERE_CHANNEL_ID or START_HERE_CHANNEL_NAMES. Tried: ${channelNames.join(', ')}`,
    );
  }
  return found;
}

async function inferGuildId() {
  const guilds = await discordRequest('GET', '/users/@me/guilds');
  if (guilds.length === 1) {
    return guilds[0].id;
  }

  const guildNames = guilds.map((guild) => `${guild.name} (${guild.id})`).join(', ');
  throw new Error(
    `DISCORD_GUILD_ID is required because bot is in ${guilds.length} guilds: ${guildNames}`,
  );
}

async function findAnchorMessage(targetChannel, recentMessages) {
  if (anchorMessageId) {
    return discordRequest(
      'GET',
      `/channels/${targetChannel.id}/messages/${anchorMessageId}`,
      null,
      [200, 404],
    );
  }

  const normalizedAnchorNames = anchorAuthorNames.map(normalizeName).filter(Boolean);
  return recentMessages.find((message) => {
    if (message.author?.bot) {
      return false;
    }
    const labels = [
      message.author?.username,
      message.author?.global_name,
      message.author?.display_name,
    ].map(normalizeName);
    return labels.some((label) => normalizedAnchorNames.some((name) => label.includes(name)));
  }) ?? null;
}

function isStartHerePrompt(message) {
  const searchableText = [
    message.content,
    ...(message.embeds ?? []).flatMap((embed) => [
      embed.title,
      embed.description,
      ...(embed.fields ?? []).flatMap((field) => [field.name, field.value]),
    ]),
  ].filter(Boolean).join('\n');

  return /Добро пожаловать в Bootcamp|Cryptomannn Academy|Что нужно сделать сейчас|Выбери одно или два направления/i
    .test(searchableText);
}

async function discordRequest(method, path, body = null, okStatuses = [200, 201, 204]) {
  const response = await fetch(`https://discord.com/api/v10${path}`, {
    method,
    headers: {
      Authorization: `Bot ${token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!okStatuses.includes(response.status)) {
    throw new Error(`${method} ${path} ${response.status}: ${await response.text()}`);
  }
  if (response.status === 204 || response.status === 404) {
    return null;
  }
  return response.json();
}

function isAfter(leftMessageId, rightMessageId) {
  return BigInt(leftMessageId) > BigInt(rightMessageId);
}

function authorLabel(author) {
  return author?.global_name || author?.username || author?.id || 'unknown';
}

function optionalString(...names) {
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (value) {
      return value;
    }
  }
  return null;
}

function optionalCsvArray(name, fallback) {
  const values = (process.env[name] ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return values.length > 0 ? values : fallback;
}

function optionalFirstCsvString(name) {
  return (process.env[name] ?? '')
    .split(',')
    .map((item) => item.trim())
    .find(Boolean) ?? null;
}

function optionalBoolean(name, fallback) {
  const value = process.env[name]?.trim().toLowerCase();
  if (!value) {
    return fallback;
  }
  return !['0', 'false', 'no', 'off'].includes(value);
}

function normalizeName(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}

function loadLocalEnv() {
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const envPath = path.resolve(scriptDir, '..', '.env');
  if (!fs.existsSync(envPath)) {
    return;
  }

  const raw = fs.readFileSync(envPath, 'utf8');
  for (const line of raw.split(/\r?\n/)) {
    const match = line.match(/^\s*([^#=\s]+)\s*=\s*(.*)\s*$/);
    if (!match) {
      continue;
    }
    const [, key, rawValue] = match;
    if (process.env[key] !== undefined) {
      continue;
    }
    process.env[key] = unquoteEnvValue(rawValue);
  }
}

function unquoteEnvValue(value) {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"'))
      || (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}
