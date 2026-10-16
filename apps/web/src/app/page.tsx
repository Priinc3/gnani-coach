"use client";

import { useState, type ChangeEvent } from "react";
import catalog from "@gnani/contracts/data/catalog.json";

const { scenarios, languages, levels } = catalog;

export default function HomePage() {
  const [scenarioId, setScenarioId] = useState(scenarios[0].id);
  const [practiceLanguageId, setPracticeLanguageId] = useState(languages[0].id);
  const [coachingLanguageId, setCoachingLanguageId] = useState(languages[0].id);
  const [coachingLanguageChosen, setCoachingLanguageChosen] = useState(false);
  const [levelId, setLevelId] = useState(levels[0].id);
  const [recordingRetention, setRecordingRetention] = useState(false);

  const scenario = scenarios.find((entry) => entry.id === scenarioId) ?? scenarios[0];
  const practiceLanguage =
    languages.find((entry) => entry.id === practiceLanguageId) ?? languages[0];
  const coachingLanguage =
    languages.find((entry) => entry.id === coachingLanguageId) ?? languages[0];
  const level = levels.find((entry) => entry.id === levelId) ?? levels[0];

  function handlePracticeLanguageChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextId = event.target.value;
    setPracticeLanguageId(nextId);
    if (!coachingLanguageChosen) {
      setCoachingLanguageId(nextId);
    }
  }

  function handleCoachingLanguageChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextId = event.target.value;
    setCoachingLanguageId(nextId);
    setCoachingLanguageChosen(nextId !== practiceLanguageId);
  }

  return (
    <main className="page">
      <div className="masthead-col">
        <header className="masthead">
          <p className="wordmark">Speaking Coach</p>
          <h1>Practice speaking, not just studying.</h1>
          <p className="lede">
            A calm conversation studio for live spoken practice: interview answers, workplace
            exchanges, everyday situations and travel small talk, with short coaching breaks
            between rounds.
          </p>
          <p className="masthead-status">
            Foundation build for an adults-only pilot. Everything on this page runs locally: no
            provider is connected, the microphone stays off, and nothing is stored.
          </p>
        </header>
      </div>

      <div className="studio-col">
        <section className="panel" aria-labelledby="setup-heading">
          <h2 id="setup-heading">Set up today&rsquo;s practice</h2>

          <fieldset className="field scenario-field">
            <legend>What do you want to practise?</legend>
            <div className="scenario-options">
              {scenarios.map((entry) => (
                <label className="scenario-option" key={entry.id} htmlFor={`scenario-${entry.id}`}>
                  <input
                    type="radio"
                    id={`scenario-${entry.id}`}
                    name="scenario"
                    value={entry.id}
                    checked={scenarioId === entry.id}
                    onChange={() => setScenarioId(entry.id)}
                  />
                  <span className="scenario-name">{entry.displayName}</span>
                  <span className="scenario-description">{entry.description}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="field">
            <label htmlFor="practice-language">What language do you want to practise?</label>
            <select
              id="practice-language"
              value={practiceLanguageId}
              onChange={handlePracticeLanguageChange}
            >
              {languages.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.displayName} — {entry.nativeName}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="coaching-language">What language should the coach explain in?</label>
            <select
              id="coaching-language"
              value={coachingLanguageId}
              onChange={handleCoachingLanguageChange}
              aria-describedby="coaching-language-help"
            >
              {languages.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.displayName} — {entry.nativeName}
                </option>
              ))}
            </select>
            <p className="field-help" id="coaching-language-help">
              Starts the same as your practice language and follows it until you choose otherwise.
              Cross-language coaching pairs have not been tested yet.
            </p>
          </div>

          <div className="field">
            <label htmlFor="level">How comfortable are you right now?</label>
            <select id="level" value={levelId} onChange={(event) => setLevelId(event.target.value)}>
              {levels.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.displayName}
                </option>
              ))}
            </select>
          </div>

          <div className="field checkbox-field">
            <input
              type="checkbox"
              id="recording-retention"
              checked={recordingRetention}
              onChange={(event) => setRecordingRetention(event.target.checked)}
              aria-describedby="recording-retention-help"
            />
            <div>
              <label htmlFor="recording-retention">Save the session recording for replay</label>
              <p className="field-help" id="recording-retention-help">
                Off by default. If you turn this on in a later build, only the call audio would be
                kept so you can replay it — transcripts and coaching notes always stay transient
                and are never added to saved history. In this foundation build nothing is recorded
                or saved at all.
              </p>
            </div>
          </div>

          <div className="start-area">
            <button
              type="button"
              className="start-button"
              disabled
              aria-describedby="start-reason"
            >
              Start live practice call
            </button>
            <p className="start-reason" id="start-reason">
              Live calling will be enabled after speech-provider setup.
            </p>
          </div>

          <p className="plan-summary" role="status">
            Plan: {scenario.displayName} · practising {practiceLanguage.displayName} (
            {practiceLanguage.nativeName}) · coach explains in {coachingLanguage.displayName} ·{" "}
            {level.displayName.toLowerCase()} level · 4 turns per coaching round · up to 5 minutes
            ·{" "}
            {recordingRetention
              ? "recording would be kept for replay (audio only; transcripts stay transient)"
              : "recording not saved"}
          </p>

          <details className="preview">
            <summary>Optional: see a sample coaching break</summary>
            <div className="preview-body">
              <p className="preview-label">sample preview — no live AI or recording</p>
              <p className="preview-quote">
                &ldquo;You explained the situation clearly. You paused before your main point — try
                starting with the outcome next time.&rdquo;
              </p>
              <p className="field-help">
                Static illustration of the planned coaching flow. Nothing on this page listens,
                answers or records.
              </p>
            </div>
          </details>
        </section>

        <section className="panel" aria-labelledby="languages-heading">
          <h2 id="languages-heading">The ten documented languages</h2>
          <p>
            Every entry below is read from the shared language catalog and appears in the reviewed
            realtime provider documentation. None has passed a call or coaching check in this app
            yet, so each carries the same honest label.
          </p>
          <ul className="language-list">
            {languages.map((entry) => (
              <li key={entry.id}>
                <span className="language-name">
                  {entry.displayName}{" "}
                  <span className="language-native" lang={entry.sttCode}>
                    {entry.nativeName}
                  </span>
                </span>
                <span className="badge">Not yet verified</span>
              </li>
            ))}
          </ul>
          <p className="field-help">
            Hinglish (Hindi–English mix) is tracked as a separate code-mixed mode in the catalog;
            it has not been tested either.
          </p>
        </section>

        <section className="panel" aria-labelledby="status-heading">
          <h2 id="status-heading">What is real in this build</h2>
          <ul className="honesty-list">
            <li>
              Real: this setup screen, the shared draft v0.1 contracts, and a local voice-service
              skeleton whose health check proves the process starts.
            </li>
            <li>
              Real: your microphone is never requested, and no connection, transcript, waveform or
              score is simulated.
            </li>
            <li>
              Not built yet: live speech providers, recording, audio analysis, accounts and saved
              history. Sign-in and saved history are planned, not working.
            </li>
          </ul>
        </section>

        <footer className="footer">
          <p>
            Speaking Coach — foundation build. Runs locally with no providers connected, no
            recording and no stored history.
          </p>
        </footer>
      </div>
    </main>
  );
}
