<?php

namespace Database\Seeders;

use App\Models\Page;
use Illuminate\Database\Seeder;

class ScrapedPagesSeeder extends Seeder
{
    public function run(): void
    {
        $path = database_path('seeders/scraped_seed.json');

        if (! file_exists($path)) {
            $this->command->warn("No scraped seed file found at {$path}. Run the scraper first to generate it.");
            return;
        }

        $json = json_decode(file_get_contents($path), true);
        if (! $json || ! isset($json['items'])) {
            $this->command->error('Invalid JSON structure in scraped_seed.json');
            return;
        }

        foreach ($json['items'] as $item) {
            if (isset($item['error'])) {
                $this->command->warn("Skipping {$item['slug']}: error in scraping ({$item['error']})");
                continue;
            }

            $slug = $item['slug'] ?? null;
            if (! $slug) {
                $this->command->warn('Skipping entry with missing slug');
                continue;
            }

            // normalize slug to start with '/'
            $pageSlug = '/' . ltrim($slug, '/');

            $title = $item['title'] ?: $pageSlug;

            // Build a minimal sections structure compatible with PageSeeder expectations
            $sections = [
                [
                    'type' => 'html',
                    'data' => [
                        'title' => $title,
                        'description' => $item['description'] ?? null,
                        'author' => $item['author'] ?? null,
                        'published_at' => $item['published_at'] ?? null,
                        'html' => $item['content_html'] ?? null,
                        'text' => $item['content_text'] ?? null,
                        'images' => $item['images'] ?? [],
                    ],
                ],
            ];

            Page::updateOrCreate(
                ['slug' => $pageSlug],
                ['title' => $title, 'sections' => $sections]
            );

            $this->command->info("Imported: {$pageSlug}");
        }
    }
}
