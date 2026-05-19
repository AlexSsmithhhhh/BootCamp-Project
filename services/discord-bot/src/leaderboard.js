import {
  ChannelType,
  EmbedBuilder,
  PermissionFlagsBits,
} from 'discord.js';

const POSITIVE_REACTIONS = new Set(['✅', '🔥']);
const DEFAULT_IGNORED_CHANNEL_NAME = /(?:rules|announc|welcome|start|faq|guide|leaderboard|лидер|анонс|правил)/i;

export function createLeaderboardEmbed(storage, config, { personalUserId = null } = {}) {
  const rows = storage.leaderboard(10);
  const ranking = rows.length > 0
    ? rows
      .map((user, index) => `${index + 1}. <@${user.id}> — **${user.totalPoints} баллов**`)
      .join('\n')
    : 'Пока нет начислений. Первые полезные сообщения, реакции менторов и stage дадут баллы.';

  const embed = new EmbedBuilder()
    .setTitle('Activity Leaderboard Dashboard')
    .setColor(0x2f9df4)
    .setDescription(ranking)
    .addFields(
      {
        name: 'Как начисляются баллы',
        value: [
          `+${config.scores.message} за содержательное сообщение в рабочих чатах, до ${config.scores.messageDailyCap} в день.`,
          `+${config.scores.mentorReaction} за ✅ или 🔥 от Mentor/Support, до ${config.scores.mentorReactionDailyCap} в день.`,
          `+${config.scores.stage} за stage от 15 минут, один раз в день.`,
        ].join('\n'),
      },
      {
        name: 'Награды',
        value: '150 баллов — Discount 15%\n275 баллов — Discount 20%',
        inline: false,
      },
      {
        name: 'Финальный Top 3',
        value: '1 место — бесплатный доступ к продукту BootCamp\n2 место — 3 месяца в сообществе\n3 место — 1 месяц в сообществе',
        inline: false,
      },
      {
        name: 'Обновление',
        value: `Dashboard обновляется автоматически каждые ${Math.round(config.updateEveryMs / 60000)} минут.\nОбновлено: ${formatDateTime(new Date(), config.timeZone)}`,
      },
    );

  if (personalUserId) {
    const user = storage.state.users[personalUserId];
    const rank = storage.rankOf(personalUserId);
    embed.addFields({
      name: 'Ваш результат',
      value: user
        ? `Место: ${rank ?? '—'}\nБаллы: **${user.totalPoints}**\nСообщения: ${user.stats.messagePoints}\nРеакции: ${user.stats.reactionPoints}\nStage: ${user.stats.stagePoints}\nОт менторов: ${user.stats.manualPoints || 0}`
        : 'Пока нет начислений.',
    });
  }

  return embed;
}

export function createPersonalEmbed(storage, config, userId) {
  const user = storage.state.users[userId];
  const rank = storage.rankOf(userId);
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
            `Сообщения: ${today.messagePoints}/${config.scores.messageDailyCap}`,
            `Mentor/Support реакции: ${today.reactionPoints}/${config.scores.mentorReactionDailyCap}`,
            `Stage: ${today.stageAwarded ? 'зачтён' : 'ещё нет'}`,
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
  return POSITIVE_REACTIONS.has(reaction.emoji.name);
}

export function isMentorOrSupport(member, config) {
  if (!member) {
    return false;
  }
  if (member.permissions?.has(PermissionFlagsBits.Administrator)) {
    return true;
  }
  return member.roles.cache.some((role) => {
    const roleName = role.name.toLowerCase();
    return config.mentorRoleNames.some((name) => roleName.includes(name));
  });
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

  const embed = createLeaderboardEmbed(storage, config);
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
      await message.edit({ embeds: [embed] });
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
    await message.edit({ embeds: [embed] });
  } else {
    message = await channel.send({ embeds: [embed] });
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
