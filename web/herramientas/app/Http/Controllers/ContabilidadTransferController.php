<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Response;
use Symfony\Component\HttpFoundation\BinaryFileResponse;

class ContabilidadTransferController extends Controller
{
    public function index()
    {
        return response()
            ->view('app', [
                'payload' => [
                    'mode' => 'contabilidad-transfer',
                    'branding' => config('tools.branding', []),
                    'contabilidad' => [
                        'today' => now()->toDateString(),
                        'statusEndpoint' => route('contabilidad-transfer.status'),
                        'downloadEndpointTemplate' => route('contabilidad-transfer.download', [
                            'date' => '__DATE__',
                            'type' => '__TYPE__',
                        ]),
                    ],
                ],
            ])
            ->header('X-Robots-Tag', 'noindex, nofollow');
    }

    public function status(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'fecha' => ['required', 'date_format:Y-m-d'],
        ]);

        $date = $validated['fecha'];
        $dayDirectory = $this->dayDirectory($date);
        $metadataPath = $dayDirectory.DIRECTORY_SEPARATOR.'metadata.json';

        if (! File::exists($metadataPath)) {
            return response()
                ->json([
                    'ok' => true,
                    'found' => false,
                    'date' => $date,
                    'message' => 'No hay output generado para la fecha seleccionada.',
                ])
                ->header('X-Robots-Tag', 'noindex, nofollow');
        }

        $metadata = json_decode(File::get($metadataPath), true);
        if (! is_array($metadata)) {
            return response()
                ->json([
                    'ok' => false,
                    'found' => false,
                    'date' => $date,
                    'message' => 'El metadata del output no se pudo leer.',
                ], 500)
                ->header('X-Robots-Tag', 'noindex, nofollow');
        }

        return response()
            ->json([
                'ok' => true,
                'found' => true,
                'date' => $date,
                'metadata' => $metadata,
                'downloads' => [
                    'full' => route('contabilidad-transfer.download', ['date' => $date, 'type' => 'full']),
                    'high_matches' => route('contabilidad-transfer.download', ['date' => $date, 'type' => 'high']),
                ],
            ])
            ->header('X-Robots-Tag', 'noindex, nofollow');
    }

    public function download(string $date, string $type): BinaryFileResponse|JsonResponse
    {
        if (! preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) {
            return response()->json(['ok' => false, 'message' => 'Fecha invalida.'], 422);
        }

        if (! in_array($type, ['full', 'high'], true)) {
            return response()->json(['ok' => false, 'message' => 'Tipo de archivo invalido.'], 422);
        }

        $compactDate = str_replace('-', '', $date);
        $fileName = $type === 'high'
            ? "cruce_mov_emp_vimarx_altos_{$compactDate}.xlsx"
            : "cruce_mov_emp_vimarx_{$compactDate}.xlsx";
        $path = $this->dayDirectory($date).DIRECTORY_SEPARATOR.$fileName;

        if (! File::exists($path)) {
            return response()->json(['ok' => false, 'message' => 'Archivo no encontrado.'], 404);
        }

        return Response::download($path, $fileName, [
            'X-Robots-Tag' => 'noindex, nofollow',
        ]);
    }

    private function dayDirectory(string $date): string
    {
        return rtrim((string) config('tools.contabilidad.output_root'), DIRECTORY_SEPARATOR).DIRECTORY_SEPARATOR.$date;
    }
}
