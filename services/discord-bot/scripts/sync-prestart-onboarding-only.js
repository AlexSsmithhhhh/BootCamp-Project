const token = process.env.DISCORD_TOKEN;
const guildId = process.env.DISCORD_GUILD_ID;

if (!token || !guildId) {
  throw new Error('DISCORD_TOKEN and DISCORD_GUILD_ID are required.');
}

const P = {
  AddReactions: 1n << 6n,
  AttachFiles: 1n << 15n,
  Connect: 1n << 20n,
  CreatePrivateThreads: 1n << 36n,
  CreatePublicThreads: 1n << 35n,
  EmbedLinks: 1n << 14n,
  ReadMessageHistory: 1n << 16n,
  SendMessages: 1n << 11n,
  SendMessagesInThreads: 1n << 38n,
  Speak: 1n << 21n,
  Stream: 1n << 9n,
  UseExternalEmojis: 1n << 18n,
  ViewChannel: 1n << 10n,
};

const onboardingRoleAllow = String(
  P.ViewChannel
    | P.ReadMessageHistory
    | P.AddReactions
    | P.UseExternalEmojis,
);
const onboardingRoleDeny = String(
  P.SendMessages
    | P.SendMessagesInThreads
    | P.CreatePublicThreads
    | P.CreatePrivateThreads
    | P.Connect
    | P.Speak,
);
const hiddenDeny = String(
  P.ViewChannel
    | P.SendMessages
    | P.SendMessagesInThreads
    | P.CreatePublicThreads
    | P.CreatePrivateThreads
    | P.Connect
    | P.Speak,
);
const staffAllow = String(
  P.ViewChannel
    | P.SendMessages
    | P.SendMessagesInThreads
    | P.ReadMessageHistory
    | P.AddReactions
    | P.EmbedLinks
    | P.AttachFiles
    | P.UseExternalEmojis
    | P.Connect
    | P.Speak
    | P.Stream,
);

const channels = await discordRequest('GET', `/guilds/${guildId}/channels`);
const roles = await discordRequest('GET', `/guilds/${guildId}/roles`);
const roleByName = new Map(roles.map((role) => [normalizeName(role.name), role]));
const trader = roleByName.get('trader');
const staffRoles = ['mentor', 'moderator', 'support']
  .map((name) => roleByName.get(name))
  .filter(Boolean);
const onboarding = channels.find((channel) => (
  channel.type === 4 && normalizeName(channel.name) === 'onboarding'
));

if (!trader) {
  throw new Error('Trader role not found.');
}
if (!onboarding) {
  throw new Error('Onboarding category not found.');
}
if (staffRoles.length < 3) {
  throw new Error(`Expected Mentor, Moderator and Support roles; found ${staffRoles.map((role) => role.name).join(', ')}`);
}

const onboardingChannelIds = new Set([
  onboarding.id,
  ...channels.filter((channel) => channel.parent_id === onboarding.id).map((channel) => channel.id),
]);

for (const channel of channels) {
  const isOnboarding = onboardingChannelIds.has(channel.id);
  const allow = isOnboarding ? onboardingRoleAllow : '0';
  const deny = isOnboarding ? onboardingRoleDeny : hiddenDeny;

  await setOverwrite(channel.id, guildId, allow, deny);
  await setOverwrite(channel.id, trader.id, allow, deny);

  for (const role of staffRoles) {
    await setOverwrite(channel.id, role.id, staffAllow, '0');
  }

  console.log(`${channel.name}: ${isOnboarding ? 'visible to everyone/trader' : 'hidden from everyone/trader'}, staff visible`);
}

async function setOverwrite(channelId, targetId, allow, deny) {
  await discordRequest(
    'PUT',
    `/channels/${channelId}/permissions/${targetId}`,
    {
      type: 0,
      allow,
      deny,
    },
    [204],
  );
}

async function discordRequest(method, path, body = null, okStatuses = [200, 201, 204]) {
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    const response = await fetch(`https://discord.com/api/v10${path}`, {
      method,
      headers: {
        Authorization: `Bot ${token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await response.text();
    if (okStatuses.includes(response.status)) {
      return text ? JSON.parse(text) : null;
    }
    if (response.status === 429) {
      await sleep(retryAfterMs(text));
      continue;
    }
    throw new Error(`${method} ${path} ${response.status}: ${text}`);
  }
  throw new Error(`${method} ${path} failed after rate-limit retries.`);
}

function retryAfterMs(responseText) {
  try {
    return Math.ceil(JSON.parse(responseText).retry_after * 1000) + 250;
  } catch {
    return 1000;
  }
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function normalizeName(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}
