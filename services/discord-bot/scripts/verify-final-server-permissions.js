const token = process.env.DISCORD_TOKEN;
const guildId = process.env.DISCORD_GUILD_ID;

if (!token || !guildId) {
  throw new Error('DISCORD_TOKEN and DISCORD_GUILD_ID are required.');
}

const P = {
  Administrator: 1n << 3n,
  BanMembers: 1n << 2n,
  Connect: 1n << 20n,
  KickMembers: 1n << 1n,
  ManageChannels: 1n << 4n,
  ManageGuild: 1n << 5n,
  ManageMessages: 1n << 13n,
  ManageRoles: 1n << 28n,
  ManageThreads: 1n << 34n,
  ModerateMembers: 1n << 40n,
  MuteMembers: 1n << 22n,
  SendMessages: 1n << 11n,
  ViewChannel: 1n << 10n,
};

const traderWrite = new Set(['work-chat', 'questions', 'lounge-chat']);
const traderVoice = new Set(['stage', 'lounge-voice']);
const traderRead = new Set(['start-here', 'announcements', 'leaderboard', 'psycho', 'workspace']);
const traderCategories = new Set(['Onboarding', 'work', 'lounge', 'materials']);

const roles = await discordRequest('GET', `/guilds/${guildId}/roles`);
const channels = await discordRequest('GET', `/guilds/${guildId}/channels`);
const byName = new Map(roles.map((role) => [role.name, role]));
const requiredRoles = ['Trader', 'Mentor', 'Moderator', 'Support', 'Forex', 'Crypto'];
const missingRoles = requiredRoles.filter((name) => !byName.has(name));
if (missingRoles.length > 0) {
  throw new Error(`Missing roles: ${missingRoles.join(', ')}`);
}

const trader = byName.get('Trader');
const staff = ['Mentor', 'Moderator', 'Support'].map((name) => byName.get(name));
const tags = ['Forex', 'Crypto'].map((name) => byName.get(name));

let ok = true;

console.log('Roles');
for (const roleName of ['Cryptomannn BOT Manager', 'Mentor', 'Moderator', 'Support', 'Trader', 'Forex', 'Crypto', 'Member']) {
  const role = byName.get(roleName);
  if (!role) {
    console.log(`${roleName}: missing`);
    continue;
  }

  const flags = Object.entries(P)
    .filter(([, bit]) => has(role.permissions, bit))
    .map(([name]) => name);
  console.log(`${role.name}: position=${role.position} permissions=${flags.join(',') || 'none'}`);
}

for (const role of staff) {
  if (has(role.permissions, P.Administrator)
    || has(role.permissions, P.ManageChannels)
    || has(role.permissions, P.ManageGuild)
    || has(role.permissions, P.ManageRoles)
    || has(role.permissions, P.ManageThreads)) {
    ok = false;
  }
  if (!has(role.permissions, P.KickMembers)
    || !has(role.permissions, P.BanMembers)
    || !has(role.permissions, P.ModerateMembers)
    || !has(role.permissions, P.MuteMembers)
    || !has(role.permissions, P.ManageMessages)) {
    ok = false;
  }
}

for (const role of tags) {
  if (BigInt(role.permissions || '0') !== 0n) {
    ok = false;
  }
}

console.log('Reaction roles');
console.log(`memberRoleId=${process.env.REACTION_ROLE_MEMBER_ROLE_ID || '-'}`);
console.log(`memberRoleNames=${process.env.REACTION_ROLE_MEMBER_ROLE_NAMES || '-'}`);
console.log(`messageIds=${process.env.REACTION_ROLE_MESSAGE_IDS || '-'}`);
console.log(`forexEmojis=${process.env.REACTION_ROLE_FOREX_EMOJIS || 'default code'}`);
console.log(`cryptoEmojis=${process.env.REACTION_ROLE_CRYPTO_EMOJIS || 'default code'}`);

if (process.env.REACTION_ROLE_MEMBER_ROLE_ID !== trader.id) {
  ok = false;
}

console.log('Channels');
for (const channel of channels.sort((left, right) => (left.position ?? 0) - (right.position ?? 0))) {
  const traderOverwrite = overwrite(channel, trader.id);
  const traderView = has(traderOverwrite?.allow, P.ViewChannel);
  const traderSend = has(traderOverwrite?.allow, P.SendMessages);
  const traderConnect = has(traderOverwrite?.allow, P.Connect);
  const traderHidden = has(traderOverwrite?.deny, P.ViewChannel);

  const expectedWrite = traderWrite.has(channel.name);
  const expectedVoice = traderVoice.has(channel.name);
  const expectedRead = traderRead.has(channel.name) || traderCategories.has(channel.name);
  const expectedHidden = !(expectedWrite || expectedVoice || expectedRead);
  const traderOk = expectedWrite
    ? traderView && traderSend
    : expectedVoice
      ? traderView && traderConnect && !traderSend
      : expectedRead
        ? traderView && !traderSend
        : expectedHidden && traderHidden;

  const staffOk = staff.every((role) => {
    const staffOverwrite = overwrite(channel, role.id);
    return has(staffOverwrite?.allow, P.ViewChannel) && has(staffOverwrite?.allow, P.SendMessages);
  });
  const tagOverwriteCount = tags.filter((role) => Boolean(overwrite(channel, role.id))).length;

  if (!traderOk || !staffOk || tagOverwriteCount > 0) {
    ok = false;
  }

  console.log(
    `${channel.name}: trader=${traderOk ? 'ok' : 'bad'} staff=${staffOk ? 'ok' : 'bad'} tagOverwrites=${tagOverwriteCount}`,
  );
}

console.log(`RESULT=${ok ? 'OK' : 'CHECK_FAILED'}`);
if (!ok) {
  process.exitCode = 1;
}

function overwrite(channel, roleId) {
  return (channel.permission_overwrites || []).find((item) => item.id === roleId) || null;
}

function has(raw, bit) {
  return (BigInt(raw || '0') & bit) === bit;
}

async function discordRequest(method, path) {
  const response = await fetch(`https://discord.com/api/v10${path}`, {
    method,
    headers: {
      Authorization: `Bot ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error(`${method} ${path} ${response.status}: ${await response.text()}`);
  }
  return response.json();
}
