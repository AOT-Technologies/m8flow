import React from "react";
import { Link } from "react-router-dom";
import { Visibility, GetApp } from "@mui/icons-material";
import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableContainer,
  IconButton,
  Typography,
} from "@mui/material";
import TemplateService from "../services/TemplateService";
import type { Template, TemplateFile } from "../types/template";

const SUPPORTED_EXT = /\.(bpmn|json|dmn|md)$/i;

function isSupportedFile(f: TemplateFile): boolean {
  return SUPPORTED_EXT.test(f.fileName);
}

function getFileViewPath(templateId: number, fileName: string): string {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".bpmn") || lower.endsWith(".dmn")) {
    return `/templates/${templateId}/files/${encodeURIComponent(fileName)}`;
  }
  if (lower.endsWith(".json") || lower.endsWith(".md")) {
    return `/templates/${templateId}/form/${encodeURIComponent(fileName)}`;
  }
  return `/templates/${templateId}`;
}

interface TemplateFileListProps {
  template: Template;
  templateId: number;
}

export default function TemplateFileList({ template, templateId }: TemplateFileListProps) {
  const files = (template.files ?? []).filter(isSupportedFile);
  const primaryFileName = files.find((f) =>
    f.fileName.toLowerCase().endsWith(".bpmn")
  )?.fileName;

  if (files.length === 0) {
    return null;
  }

  const handleDownload = (fileName: string) => {
    TemplateService.downloadTemplateFile(templateId, fileName).catch(() => {
      // Error could be shown via a toast or parent state if needed
    });
  };

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
        Files
      </Typography>
      <TableContainer>
        <Table size="medium" className="process-model-file-table">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {files.map((f) => {
              const viewPath = getFileViewPath(templateId, f.fileName);
              const isPrimary = f.fileName === primaryFileName;
              return (
                <TableRow key={f.fileName}>
                  <TableCell className="process-model-file-table-filename" title={f.fileName}>
                    <Link to={viewPath} style={{ textDecoration: "none" }}>
                      {f.fileName}
                    </Link>
                    {isPrimary && (
                      <Typography
                        component="span"
                        variant="caption"
                        color="text.secondary"
                        sx={{ ml: 0.5 }}
                      >
                        – Primary File
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <IconButton
                      component={Link}
                      to={viewPath}
                      size="small"
                      aria-label="View file"
                      title="View"
                    >
                      <Visibility fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      aria-label="Download file"
                      title="Download"
                      onClick={() => handleDownload(f.fileName)}
                    >
                      <GetApp fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
