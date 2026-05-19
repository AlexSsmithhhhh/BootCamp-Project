const DEFAULT_CHANNEL_NAME_PATTERN = /(?:^start[-_\s]?here$|start)/i;

export async function applyReactionRole(reaction, user, config) {
  if (!reaction.message.guild || user.bot) {
    return { handled: false };
  }

  if (!isReactionRoleChannel(reaction.message.channel, config)) {
    return { handled: false };
  }

  const direction = directionForEmoji(reaction.emoji.name, config);
  if (!direction) {
    return { handled: false };
  }

  const guild = reaction.message.guild;
  const member = await guild.members.fetch(user.id);
  const memberRole = findRole(guild, {
    id: config.reactionRoles.memberRoleId,
    names: config.reactionRoles.memberRoleNames,
  });
  const directionRole = findRole(guild, {
    id: direction.roleId,
    names: direction.roleNames,
  });

  if (!memberRole || !directionRole) {
    return {
      handled: true,
      applied: false,
      reason: `missing role: member=${Boolean(memberRole)} direction=${Boolean(directionRole)}`,
    };
  }

  const rolesToAdd = [memberRole, directionRole]
    .filter((role) => !member.roles.cache.has(role.id));

  if (rolesToAdd.length > 0) {
    await member.roles.add(rolesToAdd, `BootCamp start-here reaction: ${direction.key}`);
  }

  return {
    handled: true,
    applied: true,
    direction: direction.key,
    memberRoleId: memberRole.id,
    directionRoleId: directionRole.id,
    addedRoleIds: rolesToAdd.map((role) => role.id),
  };
}

export async function removeReactionRole(reaction, user, config) {
  if (!reaction.message.guild || user.bot) {
    return { handled: false };
  }

  if (!isReactionRoleChannel(reaction.message.channel, config)) {
    return { handled: false };
  }

  const direction = directionForEmoji(reaction.emoji.name, config);
  if (!direction) {
    return { handled: false };
  }

  const guild = reaction.message.guild;
  const member = await guild.members.fetch(user.id).catch(() => null);
  if (!member) {
    return { handled: true, removed: false, reason: 'member not found' };
  }

  const directionRole = findRole(guild, {
    id: direction.roleId,
    names: direction.roleNames,
  });
  if (!directionRole) {
    return { handled: true, removed: false, reason: `missing role: ${direction.key}` };
  }

  if (member.roles.cache.has(directionRole.id)) {
    await member.roles.remove(directionRole, `BootCamp start-here reaction removed: ${direction.key}`);
  }

  return {
    handled: true,
    removed: true,
    direction: direction.key,
    directionRoleId: directionRole.id,
  };
}

export function directionForEmoji(rawEmojiName, config) {
  const emojiName = normalizeEmoji(rawEmojiName);
  for (const direction of config.reactionRoles.directions) {
    if ([...direction.emojis].some((emoji) => normalizeEmoji(emoji) === emojiName)) {
      return direction;
    }
  }
  return null;
}

export function isReactionRoleChannel(channel, config) {
  if (!channel) {
    return false;
  }
  if (config.reactionRoles.channelIds.size > 0) {
    return config.reactionRoles.channelIds.has(channel.id);
  }
  return DEFAULT_CHANNEL_NAME_PATTERN.test(channel.name ?? '');
}

export function normalizeEmoji(value) {
  return (value ?? '').replace(/\uFE0F/g, '').trim();
}

function findRole(guild, { id, names }) {
  if (id) {
    const role = guild.roles.cache.get(id);
    if (role) {
      return role;
    }
  }

  const normalizedNames = names.map((name) => name.toLowerCase());
  return guild.roles.cache.find((role) => normalizedNames.includes(role.name.toLowerCase())) ?? null;
}
