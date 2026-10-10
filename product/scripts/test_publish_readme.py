import unittest

from publish_readme import IMAGE_SOURCE, ROOT, build_assets, inline, render_readme, safe_link


class ReadmePublicationTests(unittest.TestCase):
    def test_raw_html_cannot_execute(self):
        rendered = render_readme('# GameBuddy\n\n<script>alert(1)</script>\n')
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_unsafe_links_are_rejected(self):
        for target in ('javascript:alert', 'data:text/html,hello', 'http://example.com',
                       'https://user:password@example.com', '//example.com',
                       '../README.md', '/README.md'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                safe_link(target)

    def test_missing_repository_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_link('docs/missing-readme-source.md')

    def test_images_require_an_explicit_public_source(self):
        for path in ('data/正式视频.mp4', 'README.md', 'https://example.com/photo.jpg'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                inline(f'![photo]({path})')
        self.assertIn('src="/readme-assets/overview.jpg"', inline(f'![photo]({IMAGE_SOURCE})'))

    def test_handoff_notice_stays_out_of_visitor_page(self):
        rendered = render_readme('Internal handoff note\n\n# GameBuddy\n\nPublic product description\n')
        self.assertNotIn('Internal handoff note', rendered)
        self.assertIn('Public product description', rendered)
        self.assertIn('TEAM 02', rendered)

    def test_incomplete_source_fails_instead_of_publishing_blank_page(self):
        with self.assertRaises(ValueError):
            render_readme('# Another project\n')

    def test_unsupported_blocks_fail_before_upload(self):
        with self.assertRaises(ValueError):
            render_readme('# GameBuddy\n\n```javascript\n')

    def test_real_readme_has_all_innovations_and_bounded_assets(self):
        source = (ROOT / 'README.md').read_text(encoding='utf-8')
        assets = build_assets(source)
        rendered = assets[0]['body'].decode('utf-8')
        for number in range(1, 17):
            self.assertIn(f'id="innovation-{number:02d}"', rendered)
        self.assertEqual({asset['key'] for asset in assets}, {
            'readme', 'product/readme', 'readme/index.html', 'product/readme/index.html',
            'readme.md', 'readme-assets/overview.jpg'})
        self.assertTrue(all(asset['body'] == assets[0]['body'] for asset in assets[:4]))


if __name__ == '__main__':
    unittest.main()
