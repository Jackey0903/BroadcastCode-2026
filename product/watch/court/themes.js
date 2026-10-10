/** User-selected NBA SVG assets are bundled locally for every team skin. */
const logoURL = name => new URL(`../assets/teams/${name}.svg`, import.meta.url).href;
export const COURT_THEMES = Object.freeze({
  houston: { logo: logoURL('houston-rockets'), city: 'HOUSTON', name: 'ROCKETS', short: 'HOU', caption: '休斯顿火箭', paint: '#c20d36', wood: '#dfb57b', line: '#fff9e8' },
  dallas: { logo: logoURL('dallas-mavericks'), city: 'DALLAS', name: 'MAVERICKS', short: 'DAL', caption: '达拉斯独行侠', paint: '#1261aa', wood: '#dfb57b', line: '#fff9e8' },
  neutral: { city: 'BASKETBALL', name: 'COURT', short: 'BC', caption: '中性球场', paint: '#36536d', wood: '#dfb57b', line: '#fff9e8' },
});
export function getCourtTheme(id) {
  const aliases = { rockets: 'houston', mavericks: 'dallas', HOU: 'houston', DAL: 'dallas' };
  return COURT_THEMES[aliases[id] || id] || COURT_THEMES.neutral;
}
