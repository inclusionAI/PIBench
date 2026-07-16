import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('logger', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it('should initialize pino with default level "info" when LOG_LEVEL is not set', async () => {
    const pinoMock = vi.fn().mockReturnValue({});
    vi.doMock('pino', () => ({
      default: pinoMock,
    }));

    await import('../../src/utils/logger.js');

    expect(pinoMock).toHaveBeenCalledWith(
      expect.objectContaining({
        level: 'info',
      })
    );
  });

  it('should initialize pino with level from LOG_LEVEL environment variable', async () => {
    vi.stubEnv('LOG_LEVEL', 'debug');
    const pinoMock = vi.fn().mockReturnValue({});
    vi.doMock('pino', () => ({
      default: pinoMock,
    }));

    await import('../../src/utils/logger.js');

    expect(pinoMock).toHaveBeenCalledWith(
      expect.objectContaining({
        level: 'debug',
      })
    );
  });

  it('should use pino-pretty transport when NODE_ENV is not production', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const pinoMock = vi.fn().mockReturnValue({});
    vi.doMock('pino', () => ({
      default: pinoMock,
    }));

    await import('../../src/utils/logger.js');

    expect(pinoMock).toHaveBeenCalledWith(
      expect.objectContaining({
        transport: {
          target: 'pino-pretty',
          options: {
            colorize: true,
            translateTime: 'SYS:standard',
          },
        },
      })
    );
  });

  it('should NOT use pino-pretty transport when NODE_ENV is production', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    const pinoMock = vi.fn().mockReturnValue({});
    vi.doMock('pino', () => ({
      default: pinoMock,
    }));

    await import('../../src/utils/logger.js');

    expect(pinoMock).toHaveBeenCalledWith(
      expect.objectContaining({
        transport: undefined,
      })
    );
  });
});
