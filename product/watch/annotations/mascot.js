/** Original little basketball character. No licensed character or external artwork. */
export function mascotSVG(size = 40, options = {}) {
  const dimension = Math.max(16, Math.min(160, Number(size) || 40));
  const color = /^#[0-9a-f]{3,8}$/i.test(options.color || '') ? options.color : '#f69529';
  const focus = options.expression === 'focus';
  const minimal = options.style === 'minimal';
  const mouth = focus ? '<path d="M28 38Q33 35 38 38"/>' : '<path d="M27 36Q33 46 40 35Q33 39 27 36Z" fill="#78341d"/><path d="M30 38L36 38" stroke="#fff4d7" stroke-width="2"/>';
  return `<svg class="mascot-svg" xmlns="http://www.w3.org/2000/svg" width="${dimension}" height="${dimension}" viewBox="0 0 64 64" role="img" aria-label="原创篮球吉祥物" fill="none">
    <g stroke="#773a20" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
      ${minimal ? '' : `<path d="M14 32L8 39 5 34M49 30L55 24 59 29" stroke="${color}" stroke-width="4"/><path d="M24 49L22 56M40 49L43 56" stroke="${color}" stroke-width="4"/><path d="M17 57Q22 54 27 57M38 58Q43 54 49 57" stroke="#fff3cc" stroke-width="3.4"/>`}
      <circle cx="32" cy="29" r="22" fill="${color}"/>
      <path d="M12 22Q31 29 52 22M12 37Q33 30 53 35M29 8Q39 29 30 50M17 12Q31 29 17 45M45 12Q35 26 47 44" stroke-opacity=".67"/>
      ${minimal ? '' : '<path d="M17 19Q20 13 27 12" stroke="#fff3cb" stroke-width="3" stroke-opacity=".6"/>'}
      <ellipse cx="25" cy="28" rx="4.3" ry="6" fill="#fff9e5"/><ellipse cx="39" cy="27" rx="4.3" ry="6" fill="#fff9e5"/>
      <ellipse cx="26" cy="29" rx="1.7" ry="2.8" fill="#30313b" stroke="none"/><ellipse cx="40" cy="28" rx="1.7" ry="2.8" fill="#30313b" stroke="none"/>
      ${focus ? '<path d="M21 20L28 23M35 22L42 18" stroke-width="2.5"/>' : '<path d="M20 19Q24 16 28 18M36 17Q40 15 44 18"/>'}${mouth}
    </g></svg>`;
}
