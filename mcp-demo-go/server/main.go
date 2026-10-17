package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const maxFileBytes = 64 * 1024
const maxEntries = 100

// JSON字段名是客户端实际发送的名字
type PathInput struct {
	Path string `json:"path" jsonschema:"Path relative to the configured root; use . for its top directory"`
}

type Entry struct {
	Name  string `json:"name"`
	IsDir bool   `json:"is_dir"`
}

type DirectoryResult struct {
	Entries   []Entry `json:"entries"`
	Truncated bool    `json:"truncated"`
}

type FileResult struct {
	Path string `json:"path"`
	Text string `json:"text"`
}

// 所有打开操作都经过 os.Root, 而不是只做字符串前缀判断
func openLocal(root *os.Root, name string) (*os.File, error) {
	if !filepath.IsLocal(name) {
		return nil, fmt.Errorf("请使用根目录内的相对路径,例如 . 或 notes/hello.txt")
	}
	file, err := root.Open(name)

	if err != nil {
		return nil, fmt.Errorf("无法打开 %q;请检查路径,权限和根目录范围", name)
	}
	return file, nil
}

func main() {
	rootPath := flag.String("root", "./workspace", "Directory available to this server")
	flag.Parse()

	root, err := os.OpenRoot(*rootPath)
	if err != nil {
		log.Fatal("无法打开根目录: ", err)
	}
	defer root.Close()

	server := mcp.NewServer(
		&mcp.Implementation{Name: "filesystem-demo", Version: "0.1.0"},
		&mcp.ServerOptions{
			Instructions: "先列目录,再读取需要的文本.所有路径相对于配置的根目录;此服务不提供写入或删除.",
		},
	)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_directory",
		Description: "列出指定目录的至多 100 个条目.path 为根目录内相对路径,. 表示根目录.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input PathInput) (*mcp.CallToolResult, DirectoryResult, error) {
		file, err := openLocal(root, input.Path)
		if err != nil {
			return nil, DirectoryResult{}, err
		}
		defer file.Close()

		items, err := file.ReadDir(maxEntries + 1)
		if err != nil && err != io.EOF {
			return nil, DirectoryResult{}, fmt.Errorf("无法列目录：请确认 %q 是目录", input.Path)
		}
		trucated := len(items) > maxEntries
		if trucated {
			items = items[:maxEntries]
		}
		sort.Slice(items, func(i, j int) bool { return items[i].Name() < items[j].Name() })

		entries := make([]Entry, 0, len(items))
		for _, item := range items {
			entries = append(entries, Entry{Name: item.Name(), IsDir: item.IsDir()})
		}
		return nil, DirectoryResult{Entries: entries, Truncated: trucated}, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "read_text_file",
		Description: "读取根目录内不超过 64 KiB 的 UTF-8 文本文件；不接受目录、过大文件或含 NUL 的内容。",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input PathInput) (*mcp.CallToolResult, FileResult, error) {
		file, err := openLocal(root, input.Path)
		if err != nil {
			return nil, FileResult{}, err
		}
		defer file.Close()

		info, err := file.Stat()
		if err != nil || !info.Mode().IsRegular() {
			return nil, FileResult{}, fmt.Errorf("请提供普通文本文件的路径")
		}

		data, err := io.ReadAll(io.LimitReader(file, maxFileBytes))
		if err != nil {
			return nil, FileResult{}, fmt.Errorf("读取 %q 失败", input.Path)
		}
		if len(data) > maxFileBytes {
			return nil, FileResult{}, fmt.Errorf("文本超过 64 kiB, 请选择较小的文本")
		}
		if !utf8.Valid(data) || strings.ContainsRune(string(data), '\x00') {
			return nil, FileResult{}, fmt.Errorf("文本不是示例支持的 UTF-8 文本")
		}
		return nil, FileResult{Path: input.Path, Text: string(data)}, nil
	})

	// log 默认写 stderr, stdout 留给 MCP 报文
	log.Printf("filseystem-demmo 已启动, 根目录: %s", *rootPath)
	if err := server.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		log.Fatal(err)
	}
}
