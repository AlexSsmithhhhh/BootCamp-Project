import fs from 'node:fs/promises';
import path from 'node:path';

export class LeaderboardStorage {
  constructor(filePath, timeZone) {
    this.filePath = filePath;
    this.timeZone = timeZone;
    this.state = createInitialState();
  }

  async init() {
    await fs.mkdir(path.dirname(this.filePath), { recursive: true });
    try {
      const raw = await fs.readFile(this.filePath, 'utf8');
      this.state = normalizeState(JSON.parse(raw));
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
      await this.save();
    }
  }

  async save() {
    const temporaryPath = `${this.filePath}.tmp`;
    await fs.writeFile(temporaryPath, JSON.stringify(this.state, null, 2), 'utf8');
    await fs.rename(temporaryPath, this.filePath);
  }

  todayKey(date = new Date()) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: this.timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(date);
    const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${byType.year}-${byType.month}-${byType.day}`;
  }

  user(userLike) {
    const id = userLike.id;
    if (!this.state.users[id]) {
      this.state.users[id] = {
        id,
        username: null,
        displayName: null,
        totalPoints: 0,
        daily: {},
        stats: {
          messagePoints: 0,
          reactionPoints: 0,
          stagePoints: 0,
          manualPoints: 0,
          contentMessages: 0,
          mentorReactions: 0,
          stageAwards: 0,
        },
        lastActiveAt: null,
      };
    }

    const user = this.state.users[id];
    if (userLike.username) {
      user.username = userLike.username;
    }
    if (userLike.displayName || userLike.globalName || userLike.username) {
      user.displayName = userLike.displayName || userLike.globalName || userLike.username;
    }
    return user;
  }

  daily(user, dateKey = this.todayKey()) {
    if (!user.daily[dateKey]) {
      user.daily[dateKey] = {
        messagePoints: 0,
        reactionPoints: 0,
        stageAwarded: false,
      };
    }
    return user.daily[dateKey];
  }

  async awardMessage(userLike, meta, scores) {
    if (meta.messageId && this.state.awardedMessages[meta.messageId]) {
      return { awarded: 0, duplicate: true };
    }

    const user = this.user(userLike);
    const eventDate = dateFromMeta(meta);
    const daily = this.daily(user, this.todayKey(eventDate));
    const award = Math.min(scores.message, Math.max(0, scores.messageDailyCap - daily.messagePoints));
    if (award <= 0) {
      return { awarded: 0, capped: true };
    }

    daily.messagePoints += award;
    user.totalPoints += award;
    user.stats.messagePoints += award;
    user.stats.contentMessages += 1;
    user.lastActiveAt = new Date().toISOString();
    if (meta.messageId) {
      this.state.awardedMessages[meta.messageId] = user.id;
    }
    this.addEvent(user.id, 'message', award, meta, meta.createdAt);
    await this.save();
    return { awarded: award, capped: false };
  }

  async awardReaction(userLike, meta, scores) {
    const reactionKey = reactionAwardKey(meta);
    if (reactionKey && this.state.awardedReactions[reactionKey]) {
      return { awarded: 0, duplicate: true };
    }

    const user = this.user(userLike);
    const eventDate = dateFromMeta(meta);
    const daily = this.daily(user, this.todayKey(eventDate));
    const award = Math.min(
      scores.mentorReaction,
      Math.max(0, scores.mentorReactionDailyCap - daily.reactionPoints),
    );
    if (award <= 0) {
      return { awarded: 0, capped: true };
    }

    daily.reactionPoints += award;
    user.totalPoints += award;
    user.stats.reactionPoints += award;
    user.stats.mentorReactions += 1;
    user.lastActiveAt = new Date().toISOString();
    if (reactionKey) {
      this.state.awardedReactions[reactionKey] = user.id;
    }
    this.addEvent(user.id, 'mentor_reaction', award, meta, meta.createdAt);
    await this.save();
    return { awarded: award, capped: false };
  }

  async awardManual(userLike, meta, points) {
    const award = Number(points);
    if (!Number.isInteger(award) || award <= 0) {
      return { awarded: 0, reason: 'invalid_points' };
    }

    const user = this.user(userLike);
    user.totalPoints += award;
    user.stats.manualPoints = (user.stats.manualPoints || 0) + award;
    user.lastActiveAt = new Date().toISOString();
    this.addEvent(user.id, 'manual_award', award, meta);
    await this.save();
    return { awarded: award, totalPoints: user.totalPoints };
  }

  async startStageSession(userLike, channelId) {
    this.user(userLike);
    this.state.stageSessions[userLike.id] = {
      channelId,
      joinedAt: new Date().toISOString(),
    };
    await this.save();
  }

  async finishStageSession(userLike, meta, scores) {
    const session = this.state.stageSessions[userLike.id];
    delete this.state.stageSessions[userLike.id];

    if (!session) {
      await this.save();
      return { awarded: 0, durationMs: 0, reason: 'missing_session' };
    }

    const durationMs = Date.now() - Date.parse(session.joinedAt);
    const user = this.user(userLike);
    const daily = this.daily(user);
    if (durationMs < scores.stageMinMs) {
      await this.save();
      return { awarded: 0, durationMs, reason: 'too_short' };
    }
    if (daily.stageAwarded) {
      await this.save();
      return { awarded: 0, durationMs, reason: 'daily_cap' };
    }

    daily.stageAwarded = true;
    user.totalPoints += scores.stage;
    user.stats.stagePoints += scores.stage;
    user.stats.stageAwards += 1;
    user.lastActiveAt = new Date().toISOString();
    this.addEvent(user.id, 'stage', scores.stage, {
      ...meta,
      durationMs,
      channelId: session.channelId,
    });
    await this.save();
    return { awarded: scores.stage, durationMs, reason: null };
  }

  async setDashboard(channelId, messageId) {
    this.state.dashboard = {
      channelId,
      messageId,
      updatedAt: new Date().toISOString(),
    };
    await this.save();
  }

  addEvent(userId, type, points, meta, createdAt = null) {
    this.state.events.push({
      userId,
      type,
      points,
      meta,
      createdAt: createdAt || new Date().toISOString(),
    });
    if (this.state.events.length > 1000) {
      this.state.events = this.state.events.slice(-1000);
    }
  }

  leaderboard(limit = 10, { excludedUserIds = new Set() } = {}) {
    return Object.values(this.state.users)
      .filter((user) => !excludedUserIds.has(user.id))
      .sort((left, right) => {
        if (right.totalPoints !== left.totalPoints) {
          return right.totalPoints - left.totalPoints;
        }
        return String(left.displayName || left.username || left.id).localeCompare(
          String(right.displayName || right.username || right.id),
        );
      })
      .slice(0, limit);
  }

  rankOf(userId, { excludedUserIds = new Set() } = {}) {
    if (excludedUserIds.has(userId)) {
      return null;
    }
    const rows = Object.values(this.state.users)
      .filter((user) => !excludedUserIds.has(user.id))
      .sort((left, right) => right.totalPoints - left.totalPoints);
    const index = rows.findIndex((user) => user.id === userId);
    return index === -1 ? null : index + 1;
  }
}

function createInitialState() {
  return {
    version: 1,
    users: {},
    events: [],
    awardedMessages: {},
    awardedReactions: {},
    stageSessions: {},
    dashboard: {
      channelId: null,
      messageId: null,
      updatedAt: null,
    },
  };
}

function normalizeState(state) {
  return {
    ...createInitialState(),
    ...state,
    users: state.users || {},
    events: state.events || [],
    awardedMessages: {
      ...buildAwardedMessagesFromEvents(state.events || []),
      ...(state.awardedMessages || {}),
    },
    awardedReactions: {
      ...buildAwardedReactionsFromEvents(state.events || []),
      ...(state.awardedReactions || {}),
    },
    stageSessions: state.stageSessions || {},
    dashboard: {
      ...createInitialState().dashboard,
      ...(state.dashboard || {}),
    },
  };
}

function reactionAwardKey(meta) {
  if (!meta.messageId || !meta.reactorId || !meta.emoji) {
    return null;
  }
  return `${meta.messageId}:${meta.reactorId}:${meta.emoji}`;
}

function dateFromMeta(meta) {
  if (!meta.createdAt) {
    return new Date();
  }
  const date = new Date(meta.createdAt);
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function buildAwardedMessagesFromEvents(events) {
  return Object.fromEntries(
    events
      .filter((event) => event.type === 'message' && event.meta?.messageId)
      .map((event) => [event.meta.messageId, event.userId]),
  );
}

function buildAwardedReactionsFromEvents(events) {
  return Object.fromEntries(
    events
      .map((event) => [reactionAwardKey(event.meta || {}), event])
      .filter(([key, event]) => key && event.type === 'mentor_reaction')
      .map(([key, event]) => [key, event.userId]),
  );
}
