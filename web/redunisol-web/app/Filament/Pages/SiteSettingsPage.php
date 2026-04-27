<?php

namespace App\Filament\Pages;

use UnitEnum;
use App\Models\SiteSetting;
use BackedEnum;
use Filament\Actions\Action;
use Filament\Schemas\Components\Section;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;

class SiteSettingsPage extends Page
{
    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedCog6Tooth;

    protected string $view = 'filament.pages.site-settings';

    protected static ?string $title = 'Configuración del Sitio';

    protected static ?string $navigationLabel = 'Configuración General';

    protected static string|UnitEnum|null $navigationGroup = 'Configuración';

    protected static ?int $navigationSort = 10;

    public ?array $data = [];

    public function mount(): void
    {
        $this->data = [
            'legal_disclaimer'         => SiteSetting::get('legal_disclaimer', ''),
            'organization_name'        => SiteSetting::get('organization_name', 'Red Unisol'),
            'organization_description' => SiteSetting::get('organization_description', ''),
            'contact_email'            => SiteSetting::get('contact_email', ''),
            'contact_phone'            => SiteSetting::get('contact_phone', ''),
            // WhatsApp: número y mensaje por defecto (autogestionable desde Filament)
            'whatsapp_phone'           => SiteSetting::get('whatsapp_phone', ''),
            'whatsapp_message'         => SiteSetting::get('whatsapp_message', 'Hola, quisiera recibir información sobre los préstamos.'),

            'contact_address'          => SiteSetting::get('contact_address', ''),
            // Dirección legible y enlace a Google Maps (autogestionable)
            'map_address'              => SiteSetting::get('map_address', ''), // Texto que se mostrará en el footer (ej: "Av. Colón 123, Córdoba")
            'map_url'                  => SiteSetting::get('map_url', ''),     // URL completa de Google Maps o link compartible
            'show_map'                 => SiteSetting::get('show_map', '1'),
            'facebook_url'             => SiteSetting::get('facebook_url', ''),
            'instagram_url'            => SiteSetting::get('instagram_url', ''),
            'linkedin_url'             => SiteSetting::get('linkedin_url', ''),
            'youtube_url'              => SiteSetting::get('youtube_url', ''),
        ];

        $this->form->fill($this->data);
    }

    public function form(Schema $schema): Schema
    {
        return $schema->schema([

            Section::make('Disclaimer Legal')
                ->description('Texto legal que aparece en el footer del sitio (tasas, condiciones, etc.)')
                ->schema([
                    Textarea::make('legal_disclaimer')
                        ->label('Texto del Disclaimer')
                        ->rows(10)
                        ->columnSpanFull(),
                ]),

            Section::make('Información de la Organización')
                ->schema([
                    TextInput::make('organization_name')
                        ->label('Nombre de la organización')
                        ->default('Red Unisol'),

                    TextInput::make('contact_email')
                        ->label('Email de contacto')
                        ->email(),

                    TextInput::make('contact_phone')
                        ->label('Teléfono de contacto'),

                    // WhatsApp fields (editable desde Filament)
                    TextInput::make('whatsapp_phone')
                        ->label('WhatsApp (teléfono)')
                        ->helperText('Número en formato internacional. Ej: 5493511234567')
                        ->nullable(),

                    Textarea::make('whatsapp_message')
                        ->label('Mensaje por defecto de WhatsApp')
                        ->helperText('Mensaje que se prellenará al abrir WhatsApp. Se podrá URL-encode al usarlo en el frontend.')
                        ->rows(2)
                        ->columnSpanFull(),

                    TextInput::make('contact_address')
                        ->label('Dirección')
                        ->columnSpanFull(),

                    // Campo para mostrar dirección legible en el footer (editable)
                    TextInput::make('map_address')
                        ->label('Dirección (texto a mostrar en footer)')
                        ->helperText('Texto legible que aparecerá en el footer. Ej: Av. Colón 123, Córdoba')
                        ->nullable()
                        ->columnSpanFull(),

                    // Enlace a Google Maps (editable)
                    TextInput::make('map_url')
                        ->label('Enlace a Google Maps')
                        ->helperText('URL completa a Google Maps (ej: https://goo.gl/maps/...)')
                        ->url()
                        ->nullable()
                        ->columnSpanFull(),

                    Toggle::make('show_map')
                        ->label('Mostrar dirección en el footer')
                        ->helperText('Si está desactivado, la dirección no se muestra pero se conserva en la configuración.')
                        ->default(true)
                        ->inline(false)
                        ->columnSpanFull(),

                    Textarea::make('organization_description')
                        ->label('Descripción')
                        ->rows(3)
                        ->columnSpanFull(),
                ])
                ->columns(2),

            Section::make('Redes Sociales')
                ->schema([
                    TextInput::make('facebook_url')
                        ->label('Facebook URL')
                        ->url()
                        ->prefix('https://'),

                    TextInput::make('instagram_url')
                        ->label('Instagram URL')
                        ->url()
                        ->prefix('https://'),

                    TextInput::make('linkedin_url')
                        ->label('LinkedIn URL')
                        ->url()
                        ->prefix('https://'),

                    TextInput::make('youtube_url')
                        ->label('YouTube URL')
                        ->url()
                        ->prefix('https://'),
                ])
                ->columns(2),

        ])->statePath('data');
    }

    public function save(): void
    {
        $data = $this->form->getState();

        // Normalize WhatsApp phone number: remove everything except digits
        if (isset($data['whatsapp_phone'])) {
            $data['whatsapp_phone'] = preg_replace('/\D+/', '', (string) $data['whatsapp_phone']);
        }

        // Ensure whatsapp_message is a string (null -> empty) so the setting is persisted consistently
        if (isset($data['whatsapp_message'])) {
            $data['whatsapp_message'] = (string) $data['whatsapp_message'];
        }

        // Ensure map fields are persisted as strings (trim whitespace)
        if (isset($data['map_address'])) {
            $data['map_address'] = trim((string) $data['map_address']);
        }

        if (isset($data['map_url'])) {
            $data['map_url'] = trim((string) $data['map_url']);
        }

        // Validate WhatsApp phone (if provided): must be 8-15 digits after normalization
        if (!empty($data['whatsapp_phone']) && !preg_match('/^\d{8,15}$/', (string) $data['whatsapp_phone'])) {
            Notification::make()
                ->title('Número de WhatsApp inválido')
                ->danger()
                ->body('Ingrese un número válido en formato internacional sin espacios ni símbolos (ej. 5493511234567).')
                ->send();

            return;
        }

        // Persist show_map as '1' or '0' so it's stored consistently
        if (isset($data['show_map'])) {
            $data['show_map'] = $data['show_map'] ? '1' : '0';
        }

        foreach ($data as $key => $value) {
            SiteSetting::set($key, $value ?? '');
        }

        Notification::make()
            ->title('Configuración guardada correctamente')
            ->success()
            ->send();
    }

    protected function getHeaderActions(): array
    {
        return [
            Action::make('save')
                ->label('Guardar cambios')
                ->icon('heroicon-o-check')
                ->action('save'),
        ];
    }
}
