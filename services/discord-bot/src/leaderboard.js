import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelType,
  EmbedBuilder,
  PermissionFlagsBits,
} from 'discord.js';

const DEFAULT_IGNORED_CHANNEL_NAME = /(?:rules|announc|welcome|start|faq|guide|leaderboard|лидер|анонс|правил)/i;
export const MY_POINTS_BUTTON_ID = 'leaderboard:my-points';

export function createLeaderboardEmbed(
  storage,
  config,
  { personalUserId = null, excludedUserIds = new Set() } = {},
) {
  const rows = storage.leaderboard(config.publicLeaderboardLimit, { excludedUserIds });
  const ranking = rows.length > 0
    ? rows
      .map((user, index) => `**${index + 1}.** <@${user.id}>  ·  **${formatPoints(user.totalPoints)}**`)
      .join('\n')
    : 'Пока нет участников с баллами.';

  const embed = new EmbedBuilder()
    .setTitle('BootCamp Leaderboard')
    .setColor(0x2f9df4)
    .setDescription(ranking)
    .setFooter({
      text: `Топ ${config.publicLeaderboardLimit} · Свои баллы: кнопка ниже · ${formatDateTime(new Date(), config.timeZone)}`,
    });

  if (personalUserId) {
    const user = storage.state.users[personalUserId];
    const rank = storage.rankOf(personalUserId, { excludedUserIds });
    embed.addFields({
      name: 'Ваш результат',
      value: user
        ? `Место: ${rank ?? '—'}\nБаллы: **${user.totalPoints}**\nСообщения: ${user.stats.messagePoints}\nРеакции: ${user.stats.reactionPoints}\nStage: ${user.stats.stagePoints}\nОт менторов: ${user.stats.manualPoints || 0}`
        : 'Пока нет начислений.',
    });
  }

  return embed;
}

export function createLeaderboardComponents() {
  return [
    new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId(MY_POINTS_BUTTON_ID)
        .setLabel('Мои баллы')
        .setStyle(ButtonStyle.Primary),
    ),
  ];
}

export function createPersonalEmbed(storage, config, userId, { excludedUserIds = new Set() } = {}) {
  const user = storage.state.users[userId];
  const rank = storage.rankOf(userId, { excludedUserIds });
  const today = user ? storage.daily(user) : null;

  return new EmbedBuilder()
    .setTitle('Мои баллы BootCamp')
    .setColor(0x67d391)
    .setDescription(
      user
        ? `У тебя **${user.totalPoints} баллов**. Текущее место: **${rank ?? '—'}**.`
        : 'Пока нет начислений. Участвуй в рабочих чатах, получай реакции менторов и заходи на stage.',
    )
    .addFields(
      {
        name: 'Сегодня',
        value: user
          ? [
            `Сообщения: ${formatTodayProgress(today.messagePoints, config.scores.messageDailyCap)}`,
            `Mentor/Support реакции: ${formatTodayProgress(today.reactionPoints, config.scores.mentorReactionDailyCap)}`,
            `Stage: ${today.stagePoints || 0}`,
          ].join('\n')
          : 'Пока пусто.',
      },
      {
        name: 'Всего',
        value: user
          ? [
            `За сообщения: ${user.stats.messagePoints}`,
            `За реакции: ${user.stats.reactionPoints}`,
            `За stage: ${user.stats.stagePoints}`,
            `От менторов: ${user.stats.manualPoints || 0}`,
          ].join('\n')
          : '0',
      },
    );
}

export function isPositiveReaction(reaction) {
  return Boolean(reaction.emoji?.name);
}

export function isMentorOrSupport(member, config) {
  if (!member) {
    return false;
  }
  if (member.permissions?.has(PermissionFlagsBits.Administrator)) {
    return true;
  }
  return hasMentorRole(member, config);
}

export function hasMentorRole(member, config) {
  if (!member) {
    return false;
  }
  return member.roles.cache.some((role) => {
    const roleName = role.name.toLowerCase();
    return config.mentorRoleNames.some((name) => roleName.includes(name));
  });
}

export async function excludedLeaderboardUserIds(guild, storage, config) {
  const excluded = new Set();
  for (const userId of Object.keys(storage.state.users)) {
    const member = await guild.members.fetch(userId).catch(() => null);
    if (hasMentorRole(member, config)) {
      excluded.add(userId);
    }
  }
  return excluded;
}

export function isWorkingChannel(channel, config) {
  if (!channel) {
    return false;
  }
  if (config.ignoredChannelIds.has(channel.id)) {
    return false;
  }
  if (config.workingChannelIds.size > 0) {
    return config.workingChannelIds.has(channel.id);
  }

  const allowedTypes = new Set([
    ChannelType.GuildText,
    ChannelType.PublicThread,
    ChannelType.PrivateThread,
    ChannelType.GuildForum,
  ]);
  if (!allowedTypes.has(channel.type)) {
    return false;
  }
  if (channel.name && DEFAULT_IGNORED_CHANNEL_NAME.test(channel.name)) {
    return false;
  }
  return true;
}

export function isSubstantiveMessage(message, config) {
  const content = message.content?.trim() || '';
  if (message.author.bot || !message.guild) {
    return false;
  }
  if (content.startsWith('/') || content.startsWith('!')) {
    return false;
  }
  if (content.length < config.messageMinLength && message.attachments.size === 0) {
    return false;
  }
  const words = content.split(/\s+/).filter(Boolean);
  if (words.length < config.messageMinWords && message.attachments.size === 0) {
    return false;
  }
  const withoutUrls = content.replace(/https?:\/\/\S+/gi, '').trim();
  return withoutUrls.length > 0 || message.attachments.size > 0;
}

export function isStageChannel(channel) {
  return channel?.type === ChannelType.GuildStageVoice;
}

export function userLikeFromMemberOrUser(memberOrUser) {
  const user = memberOrUser.user ?? memberOrUser;
  return {
    id: user.id,
    username: user.username,
    globalName: user.globalName,
    displayName: memberOrUser.displayName,
  };
}

export async function updateDashboard(client, storage, config, { forceChannelId = null } = {}) {
  const fixedMessageId = config.dashboardMessageId;
  const channelId = fixedMessageId
    ? config.dashboardChannelId
    : (forceChannelId || storage.state.dashboard.channelId || config.dashboardChannelId);
  if (!channelId) {
    return { updated: false, reason: 'missing_channel' };
  }

  let channel = null;
  try {
    channel = await client.channels.fetch(channelId);
  } catch (error) {
    console.error(`Failed to fetch leaderboard dashboard channel ${channelId}:`, error);
    return { updated: false, reason: 'channel_fetch_failed', channelId };
  }

  if (!channel?.isTextBased()) {
    return { updated: false, reason: 'channel_not_text' };
  }

  const guild = channel.guild ?? await client.guilds.fetch(config.guildId);
  const excludedUserIds = await excludedLeaderboardUserIds(guild, storage, config);
  const embed = createLeaderboardEmbed(storage, config, { excludedUserIds });
  let message = null;

  if (fixedMessageId) {
    try {
      message = await channel.messages.fetch(fixedMessageId);
    } catch (error) {
      console.error(
        `Fixed leaderboard dashboard message ${fixedMessageId} was not found in channel ${channel.id}. ` +
          'No new dashboard message will be created while LEADERBOARD_MESSAGE_ID is set.',
        error,
      );
      return {
        updated: false,
        reason: 'fixed_message_not_found',
        channelId: channel.id,
        messageId: fixedMessageId,
      };
    }

    try {
      await message.edit({ embeds: [embed], components: createLeaderboardComponents() });
    } catch (error) {
      console.error(
        `Failed to edit fixed leaderboard dashboard message ${fixedMessageId}. ` +
          'Check that the message belongs to this bot and that it can edit messages in the dashboard channel.',
        error,
      );
      return {
        updated: false,
        reason: 'fixed_message_edit_failed',
        channelId: channel.id,
        messageId: fixedMessageId,
      };
    }

    await storage.setDashboard(channel.id, message.id);
    return { updated: true, messageId: message.id, fixed: true };
  }

  if (storage.state.dashboard.messageId) {
    try {
      message = await channel.messages.fetch(storage.state.dashboard.messageId);
    } catch {
      message = null;
    }
  }

  if (message) {
    await message.edit({ embeds: [embed], components: createLeaderboardComponents() });
  } else {
    message = await channel.send({ embeds: [embed], components: createLeaderboardComponents() });
    try {
      await message.pin('BootCamp leaderboard dashboard');
    } catch {
      // Pinning is a nice-to-have; the bot may not have Manage Messages.
    }
  }

  await storage.setDashboard(channel.id, message.id);
  return { updated: true, messageId: message.id };
}

function formatDateTime(date, timeZone) {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone,
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date);
}

function formatPoints(points) {
  const absolute = Math.abs(points);
  const lastTwo = absolute % 100;
  const lastOne = absolute % 10;
  if (lastTwo >= 11 && lastTwo <= 14) {
    return `${points} баллов`;
  }
  if (lastOne === 1) {
    return `${points} балл`;
  }
  if (lastOne >= 2 && lastOne <= 4) {
    return `${points} балла`;
  }
  return `${points} баллов`;
}

function formatTodayProgress(value, cap) {
  if (!Number.isFinite(cap)) {
    return `${value}`;
  }
  return `${value}/${cap}`;
}
