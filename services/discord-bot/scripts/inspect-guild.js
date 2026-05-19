const guildId = process.env.DISCORD_GUILD_ID;
const token = process.env.DISCORD_TOKEN;

if (!guildId || !token) {
  throw new Error('DISCORD_GUILD_ID and DISCORD_TOKEN are required.');
}

async function discordGet(path) {
  const response = await fetch(`https://discord.com/api/v10${path}`, {
    headers: {
      Authorization: `Bot ${token}`,
    },
  });
  if (!response.ok) {
    throw new Error(`${path} ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

const channels = await discordGet(`/guilds/${guildId}/channels`);
const roles = await discordGet(`/guilds/${guildId}/roles`);

console.log('CHANNELS');
for (const channel of channels.sort((left, right) => (left.position ?? 0) - (right.position ?? 0))) {
  console.log([channel.id, channel.type, channel.name].join('\t'));
}

console.log('ROLES');
for (const role of roles.sort((left, right) => (right.position ?? 0) - (left.position ?? 0)).slice(0, 30)) {
  console.log([role.id, role.name].join('\t'));
}
