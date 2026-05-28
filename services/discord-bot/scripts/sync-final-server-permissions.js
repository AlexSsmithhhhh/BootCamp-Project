const token = process.env.DISCORD_TOKEN;
const guildId = process.env.DISCORD_GUILD_ID;

if (!token || !guildId) {
  throw new Error('DISCORD_TOKEN and DISCORD_GUILD_ID are required.');
}

const P = {
  AddReactions: 1n << 6n,
  Administrator: 1n << 3n,
  AttachFiles: 1n << 15n,
  BanMembers: 1n << 2n,
  Connect: 1n << 20n,
  DeafenMembers: 1n << 23n,
  EmbedLinks: 1n << 14n,
  KickMembers: 1n << 1n,
  ManageMessages: 1n << 13n,
  ManageNicknames: 1n << 27n,
  ModerateMembers: 1n << 40n,
  MoveMembers: 1n << 24n,
  MuteMembers: 1n << 22n,
  ReadMessageHistory: 1n << 16n,
  RequestToSpeak: 1n << 32n,
  SendMessages: 1n << 11n,
  SendMessagesInThreads: 1n << 38n,
  Speak: 1n << 21n,
  Stream: 1n << 9n,
  UseApplicationCommands: 1n << 31n,
  UseExternalEmojis: 1n << 18n,
  UseVAD: 1n << 25n,
  ViewAuditLog: 1n << 7n,
  ViewChannel: 1n << 10n,
};

const roleNames = {
  adminBot: 'cryptomannn-bot-manager',
  crypto: 'crypto',
  forex: 'forex',
  mentor: 'mentor',
  moderator: 'moderator',
  support: 'support',
  trader: 'trader',
};

const traderTextChannels = new Set(['work-chat', 'questions', 'lounge-chat']);
const traderVoiceChannels = new Set(['lounge-voice', 'stage']);
const traderReadOnlyChannels = new Set(['start-here', 'announcements', 'leaderboard', 'psycho', 'workspace']);
const traderVisibleCategories = new Set(['onboarding', 'work', 'lounge', 'materials']);

const staffRolePermissions = String(
  P.ViewAuditLog
    | P.KickMembers
    | P.BanMembers
    | P.ManageMessages
    | P.ManageNicknames
    | P.ModerateMembers
    | P.MuteMembers
    | P.DeafenMembers
    | P.MoveMembers
    | P.ViewChannel
    | P.SendMessages
    | P.SendMessagesInThreads
    | P.ReadMessageHistory
    | P.AddReactions
    | P.EmbedLinks
    | P.AttachFiles
    | P.UseExternalEmojis
    | P.UseApplicationCommands
    | P.Connect
    | P.Speak
    | P.Stream
    | P.UseVAD
    | P.RequestToSpeak,
);

const staffChannelAllow = String(
  P.ViewChannel
    | P.SendMessages
    | P.SendMessagesInThreads
    | P.ReadMessageHistory
    | P.AddReactions
    | P.EmbedLinks
    | P.AttachFiles
    | P.UseExternalEmojis
    | P.UseApplicationCommands
    | P.Connect
    | P.Speak
    | P.Stream
    | P.UseVAD
    | P.RequestToSpeak
    | P.ManageMessages,
);

const traderTextAllow = String(
  P.ViewChannel
    | P.SendMessages
    | P.SendMessagesInThreads
    | P.ReadMessageHistory
    | P.AddReactions
    | P.EmbedLinks
    | P.AttachFiles
    | P.UseExternalEmojis
    | P.UseApplicationCommands,
);
const traderVoiceAllow = String(
  P.ViewChannel
    | P.ReadMessageHistory
    | P.Connect
    | P.Speak
    | P.Stream
    | P.UseVAD
    | P.RequestToSpeak
    | P.UseApplicationCommands,
);
const traderReadOnlyAllow = String(
  P.ViewChannel
    | P.ReadMessageHistory
    | P.AddReactions
    | P.UseExternalEmojis
    | P.UseApplicationCommands,
);
const traderCategoryAllow = String(P.ViewChannel | P.ReadMessageHistory | P.UseApplicationCommands);
const traderNoWriteDeny = String(P.SendMessages | P.SendMessagesInThreads);
const traderHiddenDeny = String(P.ViewChannel | P.SendMessages | P.SendMessagesInThreads | P.Connect | P.Speak);

const roles = await discordRequest('GET', `/guilds/${guildId}/roles`);
const channels = await discordRequest('GET', `/guilds/${guildId}/channels`);
const byRoleName = new Map(roles.map((role) => [normalizeName(role.name), role]));
const byChannelId = new Map(channels.map((channel) => [channel.id, channel]));

const adminBotRole = requiredRole(byRoleName, roleNames.adminBot);
const traderRole = requiredRole(byRoleName, roleNames.trader);
const mentorRole = requiredRole(byRoleName, roleNames.mentor);
const moderatorRole = requiredRole(byRoleName, roleNames.moderator);
const supportRole = requiredRole(byRoleName, roleNames.support);
const forexRole = requiredRole(byRoleName, roleNames.forex);
const cryptoRole = requiredRole(byRoleName, roleNames.crypto);
const staffRoles = [mentorRole, moderatorRole, supportRole];
const tagRoles = [forexRole, cryptoRole];

await setRolePermissions(traderRole, '0');
await setRolePermissions(forexRole, '0');
await setRolePermissions(cryptoRole, '0');
for (const role of staffRoles) {
  await setRolePermissions(role, staffRolePermissions);
}

await discordRequest(
  'PATCH',
  `/guilds/${guildId}/roles`,
  [
    { id: adminBotRole.id, position: 7 },
    { id: mentorRole.id, position: 6 },
    { id: moderatorRole.id, position: 5 },
    { id: supportRole.id, position: 4 },
    { id: traderRole.id, position: 3 },
    { id: forexRole.id, position: 2 },
    { id: cryptoRole.id, position: 1 },
  ],
);

for (const channel of channels) {
  for (const role of tagRoles) {
    await discordRequest('DELETE', `/channels/${channel.id}/permissions/${role.id}`, null, [204, 404]);
  }

  const traderOverwrite = traderOverwriteForChannel(channel, byChannelId);
  await discordRequest(
    'PUT',
    `/channels/${channel.id}/permissions/${traderRole.id}`,
    {
      type: 0,
      allow: traderOverwrite.allow,
      deny: traderOverwrite.deny,
    },
    [204],
  );

  for (const role of staffRoles) {
    await discordRequest(
      'PUT',
      `/channels/${channel.id}/permissions/${role.id}`,
      {
        type: 0,
        allow: staffChannelAllow,
        deny: '0',
      },
      [204],
    );
  }

  console.log(
    `${channel.name}: trader=${traderOverwrite.label}; staff=write`,
  );
}

console.log('Final server permission sync completed.');

function traderOverwriteForChannel(channel, channelsById) {
  const channelName = normalizeName(channel.name);
  const parentName = normalizeName(channelsById.get(channel.parent_id)?.name);

  if (traderTextChannels.has(channelName)) {
    return { allow: traderTextAllow, deny: '0', label: 'write' };
  }
  if (traderVoiceChannels.has(channelName)) {
    return { allow: traderVoiceAllow, deny: traderNoWriteDeny, label: 'join voice/stage' };
  }
  if (traderReadOnlyChannels.has(channelName)) {
    return { allow: traderReadOnlyAllow, deny: traderNoWriteDeny, label: 'read only' };
  }
  if (channel.type === 4 && traderVisibleCategories.has(channelName)) {
    return { allow: traderCategoryAllow, deny: traderNoWriteDeny, label: 'category visible' };
  }
  if (traderVisibleCategories.has(parentName)) {
    return { allow: '0', deny: traderHiddenDeny, label: 'hidden child' };
  }
  return { allow: '0', deny: traderHiddenDeny, label: 'hidden' };
}

async function setRolePermissions(role, permissions) {
  await discordRequest(
    'PATCH',
    `/guilds/${guildId}/roles/${role.id}`,
    { permissions },
  );
}

function requiredRole(byName, name) {
  const role = byName.get(name);
  if (!role) {
    throw new Error(`Role not found: ${name}`);
  }
  return role;
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
