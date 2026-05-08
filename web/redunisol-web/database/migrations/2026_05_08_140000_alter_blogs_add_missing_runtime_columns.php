<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('blogs')) {
            return;
        }

        Schema::table('blogs', function (Blueprint $table) {
            if (! Schema::hasColumn('blogs', 'author_display')) {
                $table->string('author_display')->nullable();
            }

            if (! Schema::hasColumn('blogs', 'published_at')) {
                $table->timestamp('published_at')->nullable();
            }

            if (! Schema::hasColumn('blogs', 'excerpt')) {
                $table->text('excerpt')->nullable();
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('blogs')) {
            return;
        }

        if (Schema::hasColumn('blogs', 'author_display')) {
            Schema::table('blogs', function (Blueprint $table) {
                $table->dropColumn('author_display');
            });
        }

        if (Schema::hasColumn('blogs', 'published_at')) {
            Schema::table('blogs', function (Blueprint $table) {
                $table->dropColumn('published_at');
            });
        }

        if (Schema::hasColumn('blogs', 'excerpt')) {
            Schema::table('blogs', function (Blueprint $table) {
                $table->dropColumn('excerpt');
            });
        }
    }
};
