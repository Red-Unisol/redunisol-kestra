import { usePage } from '@inertiajs/react';
import { useEffect, useRef } from 'react';

export default function useTracking() {
    const { url } = usePage();
    const isFirstRender = useRef(true);

    useEffect(() => {
        if (isFirstRender.current) {
            isFirstRender.current = false;
            return;
        }

        window.dataLayer = window.dataLayer || [];

        window.dataLayer.push({
            event: 'pageview',
            page: url,
        });

        console.log('[Tracking] pageview:', url);
    }, [url]);
}
