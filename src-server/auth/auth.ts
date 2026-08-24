import { betterAuth } from 'better-auth/minimal'
import { drizzleAdapter } from 'better-auth/adapters/drizzle'
import { admin, twoFactor } from 'better-auth/plugins'
import { db } from '../utils/db'
import {
  REQUIRE_EMAIL_VERIFICATION,
  SITE_NAME,
  FRONT_URL,
  ADMIN_URL,
} from '../utils/config'
import { sendResetPassword, sendVerificationEmail } from './smtp'
import { genId, genIds } from 'app/src-shared/utils/id'
import { zdb } from '../zero/db'
import { mutators } from 'app/src-shared/mutators'

export const auth = betterAuth({
  appName: SITE_NAME,
  baseURL: FRONT_URL,
  trustedOrigins: [FRONT_URL, ADMIN_URL],
  database: drizzleAdapter(db, {
    provider: 'pg',
  }),
  emailAndPassword: {
    enabled: true,
    password: {
      hash: password => Bun.password.hash(password, {
        algorithm: 'argon2id',
        memoryCost: 20480,
        timeCost: 2,
      }),
      verify: ({ password, hash }) => Bun.password.verify(password, hash),
    },
    sendResetPassword: ({ user, url }) => sendResetPassword(user, url),
    requireEmailVerification: REQUIRE_EMAIL_VERIFICATION,
  },
  experimental: {
    joins: false, // TODO: enable when supports
  },
  session: {
    cookieCache: {
      enabled: true,
      maxAge: 300,
    },
  },
  plugins: [admin(), twoFactor()],
  databaseHooks: {
    user: {
      create: {
        async after(user) {
          await zdb.transaction(async tx => {
            const mutatorCtx = {
              userId: user.id,
              locale: 'en-US',
            }
            const id = genId()
            await mutators.createWorkspace.fn({
              tx,
              ctx: mutatorCtx,
              args: {
                ids: [id, ...genIds(22)],
                name: `${user.name}'s workspace`,
              },
            })
            await tx.mutate.userData.insert({
              id: user.id,
              lastWorkspaceId: id,
              perfs: {},
              data: {},
            })
          })
        },
      },
    },
  },
  emailVerification: {
    sendVerificationEmail: ({ user, url }) => sendVerificationEmail(user, url),
  },
  rateLimit: {
    enabled: true,
    customRules: {
      '/send-verification-email': {
        window: 30,
        max: 1,
      },
    },
  },
  advanced: {
    database: {
      generateId: () => genId(),
    },
  },
})
