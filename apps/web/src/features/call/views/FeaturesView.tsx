"use client";

/**
 * The features view — Phase 04.
 *
 * Desktop area 2 of the Speakify reference: six pastel-icon cards. The
 * copy only advertises what this build actually does
 * (`prompts/phase-04-call-ui/UI-REFERENCE.md` §3), so there is no invented
 * score, no fake language count and no promised capability.
 */

import styles from "../app.module.css";
import {
  ArrowLeftIcon,
  ChartIcon,
  GlobeIcon,
  LightbulbIcon,
  MicIcon,
  UsersIcon,
  WaveIcon,
} from "../components/Icon";
import { CAPABILITIES, describeCapabilityState } from "../state/capabilities";
import type { PracticeCatalog } from "../state/settings";

export interface FeaturesViewProps {
  catalog: PracticeCatalog;
  onBack: () => void;
}

export function FeaturesView({ catalog, onBack }: FeaturesViewProps) {
  const features = [
    {
      icon: <MicIcon size={24} />,
      tile: styles.tileLavender,
      title: "Real voice conversations",
      text: "One live call in your browser. You talk hands free and the coach answers out loud. There is no push-to-talk and no upload step.",
    },
    {
      icon: <WaveIcon size={24} />,
      tile: styles.tileMint,
      title: "Feedback grounded in your audio",
      text: "Pauses, speaking rate and the length of your turn are measured on your own audio clock. When a measurement is missing, the app says so instead of guessing.",
    },
    {
      icon: <UsersIcon size={24} />,
      tile: styles.tilePeach,
      title: "Scenarios that feel real",
      text: `Interviews, workplace conversations, everyday situations, travel and social chats, plus your own topic — ${catalog.scenarios.length} in all.`,
    },
    {
      icon: <GlobeIcon size={24} />,
      tile: styles.tileSky,
      title: `${catalog.languages.length} documented languages`,
      text: "Speak in one language and get the coaching explained in another. Every entry comes from the shared catalog, with its honest badge.",
    },
    {
      icon: <LightbulbIcon size={24} />,
      tile: styles.tileLavender,
      title: "One useful change at a time",
      text: "A coaching break gives at most one strength and two changes, each tied to something that was actually observed — and a retry to try it again.",
    },
    {
      icon: <ChartIcon size={24} />,
      tile: styles.tileMint,
      title: "Progress you can check",
      text: "Sign in to keep your sessions and, if you allow it, the audio to replay. Guests can still practise; they simply keep nothing.",
    },
  ];

  return (
    <div className={styles.container}>
      <button type="button" className={styles.ghostButton} onClick={onBack}>
        <ArrowLeftIcon size={18} />
        Back
      </button>

      <section aria-labelledby="features-title">
        <p className={styles.eyebrow}>What this coach does</p>
        <h2 className={styles.sectionTitle} id="features-title">
          Everything you need to practise out loud
        </h2>
        <p className={styles.sectionLede}>
          A complete speaking coach for real-life situations, with the honest limits written on the
          same page as the features.
        </p>
        <div className={styles.featureGrid}>
          {features.map((feature) => (
            <article className={styles.featureCard} key={feature.title}>
              <div className={`${styles.featureIcon} ${feature.tile}`}>{feature.icon}</div>
              <h3 className={styles.featureTitle}>{feature.title}</h3>
              <p className={styles.featureText}>{feature.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.section} aria-labelledby="capabilities-title">
        <h2 className={styles.sectionTitle} id="capabilities-title">
          What is measured, and how far that has been checked
        </h2>
        <p className={styles.sectionLede}>
          These are the capability states from the shared register. Nothing here claims a validated
          measurement, and the app never shows a number for a capability that is not available.
        </p>
        <ul className={styles.metricList}>
          {CAPABILITIES.map((capability) => (
            <li className={styles.metricItem} key={capability.id}>
              <span className={styles.metricName}>{capability.goal}</span>
              <span className={`${styles.metricValue} ${styles.metricValueMuted}`}>
                {describeCapabilityState(capability)}
              </span>
            </li>
          ))}
        </ul>
        <p className={styles.fieldHelp}>
          Counting filled pauses is the one place where a missing measurement is deliberately not
          reported as zero: the reason is always &ldquo;counting filled pauses has not been
          validated&rdquo;.
        </p>
      </section>
    </div>
  );
}

export default FeaturesView;
