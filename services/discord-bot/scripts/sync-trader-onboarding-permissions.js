const token = process.env.DISCORD_TOKEN;
const guildId = process.env.DISCORD_GUILD_ID;

if (!token || !guildId) {
  throw new Error('DISCORD_TOKEN and DISCORD_GUILD_ID are required.');
}

const traderRoleNames = new Set(['trader']);
const onboardingNames = new Set(['onboarding']);

const permissions = {
  addReactions: 1n << 6n,
  attachFiles: 1n << 15n,
  createPrivateThreads: 1n << 36n,
  createPublicThreads: 1n << 35n,
  readMessageHistory: 1n << 16n,
  sendMessages: 1n << 11n,
  sendMessagesInThreads: 1n << 38n,
  useExternalEmojis: 1n << 18n,
  viewChannel: 1n << 10n,
};

const onboardingAllow = String(
  permissions.viewChannel
    | permissions.readMessageHistory
    | permissions.addReactions
    | permissions.useExternalEmojis,
);
const onboardingDeny = String(
  permissions.sendMessages
    | permissions.sendMessagesInThreads
    | permissions.createPublicThreads
    | permissions.createPrivateThreads,
);
const hiddenDeny = String(
  permissions.viewChannel
    | permissions.sendMessages
    | permissions.sendMessagesInThreads
    | permissions.createPublicThreads
    | permissions.createPrivateThreads,
);

const channels = await discordRequest('GET', `/guilds/${guildId}/channels`);
const roles = await discordRequest('GET', `/guilds/${guildId}/roles`);
const traderRole = roles.find((role) => traderRoleNames.has(normalizeName(role.name)));
const onboardingCategory = channels.find((channel) => (
  channel.type === 4 && onboardingNames.has(normalizeName(channel.name))
));

if (!traderRole) {
  throw new Error('Trader role not found.');
}
if (!onboardingCategory) {
  throw new Error('Onboarding category not found.');
}

const onboardingChannelIds = new Set([
  onboardingCategory.id,
  ...channels
    .filter((channel) => channel.parent_id === onboardingCategory.id)
    .map((channel) => channel.id),
]);

for (const channel of channels) {
  const isOnboarding = onboardingChannelIds.has(channel.id);
  await discordRequest(
    'PUT',
    `/channels/${channel.id}/permissions/${traderRole.id}`,
    isOnboarding
      ? {
        type: 0,
        allow: onboardingAllow,
        deny: onboardingDeny,
      }
      : {
        type: 0,
        allow: '0',
        deny: hiddenDeny,
      },
    [204],
  );

  console.log(
    `${isOnboarding ? 'Trader can view' : 'Trader hidden from'}: ${channel.name}`,
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

function normalizeName(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}
