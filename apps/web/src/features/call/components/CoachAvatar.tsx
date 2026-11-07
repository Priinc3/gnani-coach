/**
 * The coach illustration — Phase 04.
 *
 * **Asset gap.** The Speakify reference (`UI.png`) uses a painted coach
 * portrait, and no equivalent asset exists in this repository: the
 * reference board itself may not be embedded as production artwork
 * (`prompts/phase-04-call-ui/UI-REFERENCE.md` §4). This file is therefore a
 * deliberately **original, geometric** inline-SVG treatment — a friendly
 * flat-illustration coach built from circles, arcs and rounded shapes in
 * the app's own palette. It is intentionally simple and is *not* a
 * reproduction of the reference artwork. The gap is reported in
 * `prompts/phase-04-call-ui/REPORT.md`.
 *
 * The illustration is decorative: it is marked `aria-hidden` and every
 * screen that shows it also has a text label.
 */

import type { SVGProps } from "react";

const SKIN = "#f2c9a8";
const SKIN_SHADE = "#e0b088";
const HAIR = "#3b2b25";
const SWEATER = "#10655a";
const SWEATER_LIGHT = "#17a67f";
const INK = "#1b1d1f";

export interface CoachAvatarProps extends SVGProps<SVGSVGElement> {
  /** The rendered size in pixels. */
  size?: number;
}

export function CoachAvatar({ size = 260, ...rest }: CoachAvatarProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 200 200"
      role="presentation"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <defs>
        <clipPath id="coach-avatar-clip">
          <circle cx="100" cy="100" r="100" />
        </clipPath>
        <linearGradient id="coach-avatar-sweater" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={SWEATER_LIGHT} />
          <stop offset="100%" stopColor={SWEATER} />
        </linearGradient>
      </defs>

      <g clipPath="url(#coach-avatar-clip)">
        <circle cx="100" cy="100" r="100" fill="#e6f5ef" />
        <circle cx="42" cy="46" r="16" fill="#eef0fd" />
        <circle cx="160" cy="66" r="10" fill="#fdeee4" />
        <circle cx="150" cy="150" r="22" fill="#e9f3fd" />

        {/* Shoulders and torso. */}
        <path
          d="M40 200c0-33 27-52 60-52s60 19 60 52z"
          fill="url(#coach-avatar-sweater)"
        />
        <path d="M100 148l-12 18 12 12 12-12z" fill="#ffffff" opacity="0.9" />

        {/* Neck and head. */}
        <rect x="88" y="116" width="24" height="30" rx="12" fill={SKIN_SHADE} />
        <ellipse cx="100" cy="88" rx="38" ry="42" fill={SKIN} />

        {/* Hair. */}
        <path
          d="M60 84c-2-27 16-46 40-46s42 17 40 44c-4-12-12-18-20-20-6 8-18 12-32 11-12-1-20 3-28 11z"
          fill={HAIR}
        />
        <path d="M138 60c9 8 13 20 12 32 3-4 5-10 5-17 0-16-7-25-17-15z" fill={HAIR} />

        {/* Face. */}
        <g stroke={INK} strokeWidth="2.4" strokeLinecap="round" fill="none">
          <path d="M79 76c3-3 8-3 11 0" />
          <path d="M110 76c3-3 8-3 11 0" />
        </g>
        <ellipse cx="84" cy="85" rx="3.4" ry="4" fill={INK} />
        <ellipse cx="115" cy="85" rx="3.4" ry="4" fill={INK} />
        <path
          d="M88 104c6 6 18 6 24 0"
          stroke={INK}
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
        />
        <circle cx="72" cy="98" r="5" fill="#f0a58f" opacity="0.5" />
        <circle cx="127" cy="98" r="5" fill="#f0a58f" opacity="0.5" />
      </g>
    </svg>
  );
}

export default CoachAvatar;
