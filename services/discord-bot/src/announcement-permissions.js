import { ChannelType } from 'discord.js';

const ANNOUNCEMENT_WRITE_PERMISSIONS = {
  ViewChannel: true,
  SendMessages: true,
  SendMessagesInThreads: true,
  ReadMessageHistory: true,
  AttachFiles: true,
  EmbedLinks: true,
};

const WRITABLE_ANNOUNCEMENT_CHANNEL_TYPES = new Set([
  ChannelType.GuildText,
  ChannelType.GuildAnnouncement,
  ChannelType.GuildForum,
  ChannelType.GuildMedia,
]);

export async function syncAnnouncementPermissions(client, config) {
  const settings = config.announcementPermissions;
  if (!settings?.enabled) {
    return { enabled: false, updated: false, reason: 'disabled' };
  }

  const guild = await client.guilds.fetch(config.guildId);
  await guild.roles.fetch();
  await guild.channels.fetch();

  const channelResult = await findAnnouncementPermissionTarget(client, guild, settings);
  if (!channelResult.channel) {
    return { enabled: true, updated: false, reason: channelResult.reason };
  }

  const roles = findAnnouncementWriterRoles(guild, settings);
  if (roles.length === 0) {
    return {
      enabled: true,
      updated: false,
      channelName: channelResult.channel.name,
      reason: 'writer roles not found',
    };
  }

  for (const role of roles) {
    await channelResult.channel.permissionOverwrites.edit(
      role.id,
      ANNOUNCEMENT_WRITE_PERMISSIONS,
      { reason: 'Allow moderators and mentors to write in announcements' },
    );
  }

  return {
    enabled: true,
    updated: true,
    channelId: channelResult.channel.id,
    channelName: channelResult.channel.name,
    sourceChannelId: channelResult.sourceChannelId,
    sourceChannelName: channelResult.sourceChannelName,
    roleIds: roles.map((role) => role.id),
    roleNames: roles.map((role) => role.name),
  };
}

async function findAnnouncementPermissionTarget(client, guild, settings) {
  if (settings.channelId) {
    const channel = await client.channels.fetch(settings.channelId).catch(() => null);
    return permissionTargetFromChannel(channel, settings.channelId);
  }

  const candidateNames = settings.channelNames.map(normalizeName).filter(Boolean);
  const channel = guild.channels.cache.find((item) => {
    if (!item?.name || !isWritablePermissionTarget(item)) {
      return false;
    }
    return candidateNames.some((candidateName) => channelNameMatches(item.name, candidateName));
  });

  if (!channel) {
    return { channel: null, reason: 'announcement channel not found' };
  }

  return { channel };
}

async function permissionTargetFromChannel(channel, channelId) {
  if (!channel) {
    return { channel: null, reason: `channel ${channelId} not found` };
  }

  if (channel.isThread?.()) {
    const parent = channel.parent ?? await channel.fetchParent().catch(() => null);
    if (!parent) {
      return { channel: null, reason: `parent channel for thread ${channelId} not found` };
    }
    if (!isWritablePermissionTarget(parent)) {
      return { channel: null, reason: `parent channel ${parent.id} cannot receive overwrites` };
    }
    return {
      channel: parent,
      sourceChannelId: channel.id,
      sourceChannelName: channel.name,
    };
  }

  if (!isWritablePermissionTarget(channel)) {
    return { channel: null, reason: `channel ${channel.id} cannot receive overwrites` };
  }

  return { channel };
}

function isWritablePermissionTarget(channel) {
  return Boolean(
    channel.guild
      && WRITABLE_ANNOUNCEMENT_CHANNEL_TYPES.has(channel.type)
      && channel.permissionOverwrites?.edit,
  );
}

function findAnnouncementWriterRoles(guild, settings) {
  const rolesById = [...settings.roleIds]
    .map((roleId) => guild.roles.cache.get(roleId))
    .filter(Boolean);

  const roleNames = settings.roleNames.map(normalizeName).filter(Boolean);
  const rolesByName = guild.roles.cache.filter((role) => (
    roleNames.includes(normalizeName(role.name))
  ));

  return [...new Map(
    [...rolesById, ...rolesByName.values()].map((role) => [role.id, role]),
  ).values()];
}

function channelNameMatches(channelName, candidateName) {
  const normalized = normalizeName(channelName);
  return normalized === candidateName
    || normalized.endsWith(`-${candidateName}`)
    || normalized.startsWith(`${candidateName}-`);
}

function normalizeName(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}
