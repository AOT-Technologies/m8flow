import { Download, Pencil } from 'lucide-react';
import { Link } from 'react-router-dom';

import { downloadTextFile } from '@/lib/download';
import {
  contentTypeForTemplateFileName,
  fetchTemplateFileContent,
  templateModelerFilePath,
  type Template,
  type TemplateFile,
} from '@/lib/templatesApi';
import { Pill } from '@/components/library/pill/Pill';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

const SUPPORTED = /\.(bpmn|json|dmn|md)$/i;

function isSupported(file: TemplateFile): boolean {
  return SUPPORTED.test(file.fileName);
}

function fileKind(file: TemplateFile): { ext: string; label: string } {
  switch (file.fileType) {
    case 'bpmn':
      return { ext: 'BPMN', label: 'BPMN' };
    case 'dmn':
      return { ext: 'DMN', label: 'DMN' };
    case 'md':
      return { ext: 'MD', label: 'Markdown' };
    case 'json':
      if (file.fileName.toLowerCase().includes('schema')) {
        return { ext: 'JSON', label: 'Form schema' };
      }
      return { ext: 'JSON', label: 'JSON' };
    default:
      return { ext: 'FILE', label: 'File' };
  }
}

export function primaryTemplateFileName(files: TemplateFile[]): string | undefined {
  return files.find((file) => file.fileType === 'bpmn')?.fileName;
}

export type TemplateFileListProps = {
  template: Template;
};

/**
 * Per-file list on template detail — each supported file opens
 * `/templates/:id/modeler/:fileName` (Templates to 100%, ticket 07).
 */
export function TemplateFileList({ template }: TemplateFileListProps) {
  const files = (template.files ?? []).filter(isSupported);
  const primaryName = primaryTemplateFileName(files);

  return (
    <Card variant="bordered" className="mx-6 mb-6 mt-4">
      <div className="px-[22px] pt-4 pb-5">
        <div className="mb-3.5">
          <h2 className="text-[15px] font-semibold text-foreground">Files</h2>
          <p className="mt-0.5 text-[12.5px] text-muted-foreground">
            BPMN, DMN, form schema, and markdown
          </p>
        </div>
        <div className="overflow-hidden rounded-xl border border-border">
          {files.length === 0 ? (
            <p className="px-4 py-8 text-center text-[13.5px] text-muted-foreground">No files yet.</p>
          ) : (
            files.map((file) => (
              <TemplateFileRow
                key={file.fileName}
                templateId={template.id}
                file={file}
                primary={file.fileName === primaryName}
              />
            ))
          )}
        </div>
      </div>
    </Card>
  );
}

function TemplateFileRow({
  templateId,
  file,
  primary,
}: {
  templateId: number;
  file: TemplateFile;
  primary: boolean;
}) {
  const kind = fileKind(file);
  const modelerHref = templateModelerFilePath(templateId, file.fileName);
  const iconTone = kind.ext === 'BPMN' ? 'bg-nav-active/15 text-info' : 'bg-muted text-muted-foreground';

  async function handleDownload() {
    const content = await fetchTemplateFileContent(templateId, file.fileName);
    downloadTextFile(file.fileName, content, contentTypeForTemplateFileName(file.fileName));
  }

  return (
    <div className="flex items-center gap-3.5 border-b border-border px-4 py-3.5 last:border-b-0">
      <div
        className={cn(
          'flex size-8 shrink-0 items-center justify-center rounded-lg font-mono text-[9.5px] font-bold',
          iconTone,
        )}
      >
        {kind.ext}
      </div>
      <div className="min-w-0 flex-1">
        <div className="break-words text-[13.5px] text-foreground">{file.fileName}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{kind.label}</div>
      </div>
      {primary ? (
        <Pill tone="info" dot={false} className="shrink-0">
          Primary
        </Pill>
      ) : null}
      <div className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
        <Link
          to={modelerHref}
          title="Edit file"
          className="flex size-7 items-center justify-center rounded-md no-underline hover:bg-muted hover:text-info"
        >
          <Pencil className="size-4" strokeWidth={1.8} aria-hidden />
        </Link>
        <button
          type="button"
          title="Download file"
          onClick={() => void handleDownload()}
          className="flex size-7 items-center justify-center rounded-md hover:bg-muted hover:text-info"
        >
          <Download className="size-4" strokeWidth={1.8} aria-hidden />
        </button>
      </div>
    </div>
  );
}
