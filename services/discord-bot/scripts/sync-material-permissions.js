const token = process.env.DISCORD_TOKEN;
const guildId = process.env.DISCORD_GUILD_ID;

if (!token || !guildId) {
  throw new Error('DISCORD_TOKEN and DISCORD_GUILD_ID are required.');
}

const targetChannelNames = new Set(
  (process.env.MATERIAL_LOCKED_CHANNEL_NAMES || 'psycho,workspace')
    .split(',')
    .map((name) => normalizeName(name))
    .filter(Boolean),
);
const moderatorRoleNames = new Set([
  'moderator',
  'moderators',
  'mod',
  'модератор',
  'модераторы',
  'модер',
]);
const adminRoleNames = new Set([
  'admin',
  'admins',
  'administrator',
  'administrators',
  'админ',
  'админы',
  'администратор',
  'администраторы',
]);

const permissions = {
  addReactions: 1n << 6n,
  administrator: 1n << 3n,
  attachFiles: 1n << 15n,
  createPrivateThreads: 1n << 36n,
  createPublicThreads: 1n << 35n,
  embedLinks: 1n << 14n,
  readMessageHistory: 1n << 16n,
  sendMessages: 1n << 11n,
  sendMessagesInThreads: 1n << 38n,
  useExternalEmojis: 1n << 18n,
  viewChannel: 1n << 10n,
};

const everyoneAllow = String(permissions.viewChannel | permissions.readMessageHistory);
const everyoneDeny = String(
  permissions.sendMessages
    | permissions.sendMessagesInThreads
    | permissions.createPublicThreads
    | permissions.createPrivateThreads,
);
const writerAllow = String(
  permissions.viewChannel
    | permissions.sendMessages
    | permissions.sendMessagesInThreads
    | permissions.readMessageHistory
    | permissions.embedLinks
    | permissions.attachFiles
    | permissions.addReactions
    | permissions.useExternalEmojis
    | permissions.createPublicThreads,
);

const channels = await discordRequest('GET', `/guilds/${guildId}/channels`);
const roles = await discordRequest('GET', `/guilds/${guildId}/roles`);
const targetChannels = channels.filter((channel) => targetChannelNames.has(normalizeName(channel.name)));

if (targetChannels.length !== targetChannelNames.size) {
  const foundNames = targetChannels.map((channel) => channel.name).join(', ') || 'none';
  throw new Error(
    `Expected channels ${[...targetChannelNames].join(', ')}, found: ${foundNames}`,
  );
}

const moderatorRoles = roles.filter((role) => moderatorRoleNames.has(normalizeName(role.name)));
if (moderatorRoles.length === 0) {
  throw new Error('Moderator role not found.');
}

const adminRoles = roles.filter((role) => (
  role.name !== '@everyone'
    && (
      adminRoleNames.has(normalizeName(role.name))
        || hasPermission(role.permissions, permissions.administrator)
    )
));
const writerRoles = uniqueRoles([...moderatorRoles, ...adminRoles]);

for (const channel of targetChannels) {
  await discordRequest(
    'PUT',
    `/channels/${channel.id}/permissions/${guildId}`,
    {
      type: 0,
      allow: everyoneAllow,
      deny: everyoneDeny,
    },
    [204],
  );

  for (const role of writerRoles) {
    await discordRequest(
      'PUT',
      `/channels/${channel.id}/permissions/${role.id}`,
      {
        type: 0,
        allow: writerAllow,
        deny: '0',
      },
      [204],
    );
  }

  console.log(
    `Updated ${channel.name}: visible to everyone, writable by ${writerRoles.map((role) => role.name).join(', ')}`,
  );
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
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function hasPermission(rawPermissions, permission) {
  return (BigInt(rawPermissions || '0') & permission) === permission;
}

function normalizeName(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}

function uniqueRoles(roles) {
  return [...new Map(roles.map((role) => [role.id, role])).values()];
}
