"use client";

/**
 * The landing view — Phase 04.
 *
 * Desktop area 1 of the Speakify reference: a left text / right
 * illustration composition, compact navigation, floating language and
 * scenario cards, and two calls to action.
 *
 * The copy is honest about what this build does: the call is real, the
 * measurements are real, and the things that are not measured are said so
 * rather than invented.
 */

import styles from "../app.module.css";
import { CoachAvatar } from "../components/CoachAvatar";
import { ArrowLeftIcon, MicIcon, SparkIcon } from "../components/Icon";
import type { PracticeCatalog } from "../state/settings";

export interface LandingViewProps {
  catalog: PracticeCatalog;
  onStart: () => void;
  onSeeFeatures: () => void;
}

export function LandingView({ catalog, onStart, onSeeFeatures }: LandingViewProps) {
  const languageCount = catalog.languages.length;
  const scenarioCount = catalog.scenarios.length;
  const presetCount = catalog.scenarios.reduce(
    (total, scenario) => total + (scenario.presets?.length ?? 0),
    0,
  );
  const defaultPractice = catalog.languages[0]?.displayName ?? "English";
  const defaultCoaching = catalog.languages[0]?.displayName ?? "English";
  const defaultLevel = catalog.levels[0]?.displayName ?? "Beginner";

  return (
    <div className={styles.container}>
      <section className={styles.hero} aria-labelledby="landing-title">
        <div>
          <p className={styles.eyebrow}>
            <SparkIcon size={14} />
            Live voice practice coach
          </p>
          <h1 className={styles.heroTitle} id="landing-title">
            Speak with <span className={styles.heroTitleAccent}>confidence</span> in real life.
          </h1>
          <p className={styles.heroLede}>
            Practise a real conversation — an interview, a meeting, an everyday errand — then
            see where you got stuck, based on your own audio, and try that one moment again.
          </p>
          <div className={styles.heroActions}>
            <button type="button" className={styles.primaryButton} onClick={onStart}>
              Start a practice call
              <ArrowLeftIcon size={18} style={{ transform: "rotate(180deg)" }} />
            </button>
            <button type="button" className={styles.secondaryButton} onClick={onSeeFeatures}>
              See what is measured
            </button>
          </div>
          <p className={styles.heroNote}>
            The call runs in this browser over one connection to our own voice service. No speech
            provider key ever reaches the page, and the recording is off until you turn it on.
          </p>
          <dl className={styles.statRow}>
            <div>
              <dd className={styles.statValue}>{languageCount} documented languages</dd>
              <dt className={styles.statLabel}>English and nine Indian languages</dt>
            </div>
            <div>
              <dd className={styles.statValue}>{scenarioCount} scenarios</dd>
              <dt className={styles.statLabel}>Plus {presetCount} workplace presets</dt>
            </div>
            <div>
              <dd className={styles.statValue}>One live call</dd>
              <dt className={styles.statLabel}>Hands free, no push to talk</dt>
            </div>
            <div>
              <dd className={styles.statValue}>Audio-grounded feedback</dd>
              <dt className={styles.statLabel}>Or a plain &ldquo;not enough evidence&rdquo;</dt>
            </div>
          </dl>
          <p className={styles.planSummary} role="status">
            A session starts like this: practising {defaultPractice}, the coach explains in{" "}
            {defaultCoaching}, {defaultLevel.toLowerCase()} level, 4 turns per coaching round, up
            to 10 minutes, recording not saved. You can change every one of those before you
            start.
          </p>
        </div>

        <div className={styles.heroArt}>
          <div className={styles.artFrame}>
            <CoachAvatar className={styles.artAvatar} />
          </div>
          <p className={`${styles.floatingCard} ${styles.floatingCardTop}`}>
            <MicIcon size={16} />
            Just talk — the coach listens
          </p>
          <p className={`${styles.floatingCard} ${styles.floatingCardBottom}`}>
            <SparkIcon size={16} />
            Feedback from your own audio
          </p>
        </div>
      </section>

      <section className={styles.section} id="languages" aria-labelledby="landing-languages-title">
        <h2 className={styles.sectionTitle} id="landing-languages-title">
          The {catalog.languages.length} documented languages
        </h2>
        <p className={styles.sectionLede}>
          Every entry below comes from the shared language catalog and appears in the reviewed
          realtime speech documentation. None has passed a call or a coaching check in this app
          yet, so each one carries the same honest badge.
        </p>
        {/* The list, name, native-name and badge primitives are styled by the
            frozen global stylesheet. */}
        <ul className="language-list">
          {catalog.languages.map((language) => (
            <li key={language.id}>
              <span className="language-name">
                {language.displayName}{" "}
                <span className="language-native" lang={language.sttCode}>
                  {language.nativeName}
                </span>
              </span>
              <span className="badge">Not yet verified</span>
            </li>
          ))}
        </ul>
        <p className={styles.fieldHelp}>
          Hinglish (Hindi–English mix) is tracked as a separate code-mixed mode in the catalog, not
          as an eleventh language, and it has not been tested either.
        </p>
      </section>
    </div>
  );
}

export default LandingView;
