import { usePage } from '@inertiajs/react';
import { WhatsappLogo } from '@phosphor-icons/react';

interface SharedProps {
    siteData?: {
        settings?: Record<string, string>;
    };
    [key: string]: unknown;
}

interface WhatsAppButtonProps {
    phone?: string | null;
    message?: string | null;
    positionClass?: string;
    showOn?: 'all' | 'mobile' | 'desktop';
}

export default function WhatsAppButton({
    phone: phoneProp = null,
    message: messageProp = null,
    showOn = 'all',
}: WhatsAppButtonProps) {
    const { siteData } = usePage<SharedProps>().props;
    const settings = siteData?.settings ?? {};

    const rawPhone = (phoneProp ?? settings['whatsapp_phone'] ?? '').trim();
    const rawMessage =
        (messageProp ?? settings['whatsapp_message'] ?? '').trim() ||
        'Hola, quisiera recibir información sobre los préstamos.'; //revisar

    const phoneDigits = rawPhone.replace(/\D+/g, '');

    if (!phoneDigits) {
        return null;
    }

    const encodedMessage = encodeURIComponent(rawMessage);
    const waUrl = `https://wa.me/${phoneDigits}?text=${encodedMessage}`;

    const visibilityClass =
        showOn === 'all'
            ? ''
            : showOn === 'mobile'
              ? 'sm:hidden'
              : showOn === 'desktop'
                ? 'hidden sm:flex'
                : '';

    return (
        <div
            className={`fixed right-4 bottom-4 z-50 ${visibilityClass}`}
            style={{ inset: 'auto', bottom: '2rem', right: '2rem' }}
        >
            <a
                href={waUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Contactar vía WhatsApp"
                className="flex h-16 w-16 items-center justify-center rounded-full border border-[#25D366] bg-white shadow-lg transition-transform hover:scale-105 focus:ring-2 focus:ring-[#25d366] focus:ring-offset-2 focus:outline-none"
            >
                <WhatsappLogo
                    size={32}
                    weight="fill"
                    className="text-[#25D366]"
                />
            </a>
        </div>
    );
}
