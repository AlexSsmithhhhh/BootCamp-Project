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
  'ANNOUNCEMENT_CHANNEL_ID',
  'ANNOUNCEMENTS_CHANNEL_ID',
  'DISCORD_ANNOUNCEMENT_CHANNEL_ID',
);
const channelNames = optionalCsvArray('ANNOUNCEMENT_CHANNEL_NAMES', [
  'announcements',
  'announcement',
  'announces',
  'news',
  'анонсы',
  'анонс',
  'объявления',
]);
const roleIds = optionalCsvArray('ANNOUNCEMENT_WRITER_ROLE_IDS', []);
const roleNames = optionalCsvArray('ANNOUNCEMENT_WRITER_ROLE_NAMES', [
  'Moderator',
  'Moderators',
  'Mod',
  'модератор',
  'модераторы',
  'модер',
  'Mentor',
  'Mentors',
  'ментор',
  'менторы',
  'наставник',
  'наставники',
]);
const dryRun = optionalBoolean('ANNOUNCEMENT_DRY_RUN', false);

const allowPermissions = (
  1n << 10n // ViewChannel
  | 1n << 11n // SendMessages
  | 1n << 14n // EmbedLinks
  | 1n << 15n // AttachFiles
  | 1n << 16n // ReadMessageHistory
  | 1n << 38n // SendMessagesInThreads
).toString();

await discordRequest('GET', '/users/@me');
guildId = guildId || await inferGuildId();

const channels = await discordRequest('GET', `/guilds/${guildId}/channels`);
const roles = await discordRequest('GET', `/guilds/${guildId}/roles`);
const channel = findAnnouncementChannel(channels);
const writerRoles = findWriterRoles(roles);

if (!channel) {
  throw new Error(
    `Announcement channel not found. Set ANNOUNCEMENT_CHANNEL_ID or ANNOUNCEMENT_CHANNEL_NAMES. Tried: ${channelNames.join(', ')}`,
  );
}
if (writerRoles.length === 0) {
  throw new Error(
    `Writer roles not found. Set ANNOUNCEMENT_WRITER_ROLE_IDS or ANNOUNCEMENT_WRITER_ROLE_NAMES. Tried: ${roleNames.join(', ')}`,
  );
}

console.log(`Announcement channel: ${channel.name} (${channel.id})`);
console.log(`Writer roles: ${writerRoles.map((role) => `${role.name} (${role.id})`).join(', ')}`);

if (dryRun) {
  console.log('Dry run enabled; no Discord permissions were changed.');
  process.exit(0);
}

for (const role of writerRoles) {
  await discordRequest(
    'PUT',
    `/channels/${channel.id}/permissions/${role.id}`,
    {
      type: 0,
      allow: allowPermissions,
      deny: '0',
    },
    [204],
  );
  console.log(`Allowed announcement writing for role: ${role.name} (${role.id})`);
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

function findAnnouncementChannel(channels) {
  if (channelId) {
    return channels.find((channel) => channel.id === channelId) ?? null;
  }

  const normalizedNames = channelNames.map(normalizeName).filter(Boolean);
  return channels.find((channel) => (
    channel.name
      && [0, 5, 15, 16].includes(channel.type)
      && normalizedNames.some((name) => channelNameMatches(channel.name, name))
  )) ?? null;
}

function findWriterRoles(roles) {
  const rolesById = roleIds
    .map((id) => roles.find((role) => role.id === id))
    .filter(Boolean);

  const normalizedNames = roleNames.map(normalizeName).filter(Boolean);
  const rolesByName = roles.filter((role) => (
    normalizedNames.includes(normalizeName(role.name))
  ));

  return [...new Map(
    [...rolesById, ...rolesByName].map((role) => [role.id, role]),
  ).values()];
}

function channelNameMatches(channelName, candidateName) {
  const normalized = normalizeName(channelName);
  return normalized === candidateName
    || normalized.endsWith(`-${candidateName}`)
    || normalized.startsWith(`${candidateName}-`);
}

async function discordRequest(method, requestPath, body = null, okStatuses = [200, 201, 204]) {
  const response = await fetch(`https://discord.com/api/v10${requestPath}`, {
    method,
    headers: {
      Authorization: `Bot ${token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!okStatuses.includes(response.status)) {
    throw new Error(`${method} ${requestPath} ${response.status}: ${await response.text()}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
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
