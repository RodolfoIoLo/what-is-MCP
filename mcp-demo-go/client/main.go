package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func run() error {
	if len(os.Args) != 3 {
		return fmt.Errorf("用法:go run ./client <server 可执行文件> <允许访问的目录>")
	}

	serverPath, err := filepath.Abs(os.Args[1])
	if err != nil {
		return err
	}

	rootPath, err := filepath.Abs(os.Args[2])
	if err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	client := mcp.NewClient(
		&mcp.Implementation{Name: "filesystem-client", Version: "0.1.0"},
		nil,
	)

	command := exec.Command(serverPath, "-root", rootPath)
	command.Stderr = os.Stderr
	session, err := client.Connect(ctx, &mcp.CommandTransport{Command: command}, nil)
	if err != nil {
		return err
	}
	defer session.Close()

	listed, err := session.ListTools(ctx, nil)
	if err != nil {
		return err
	}
	for _, tool := range listed.Tools {
		fmt.Println("工具: ", tool.Name)
	}

	// 先列目录, 再读文件, 最后验证越界路径会被拒绝
	cases := []struct {
		name string
		path string
	}{
		{"list_directory", "."},
		{"read_text_file", "hello.txt"},
		{"read_text_file", "../outside.txt"},
	}

	for _, item := range cases {
		result, err := session.CallTool(ctx, &mcp.CallToolParams{
			Name:      item.name,
			Arguments: map[string]any{"path": item.path},
		})
		if err != nil {
			return fmt.Errorf("MCP请求失败: %w", err)
		}
		fmt.Printf("\n%s(%q) is_error=%v\n", item.name, item.path, result.IsError)
		if result.IsError {
			for _, block := range result.Content {
				if text, ok := block.(*mcp.TextContent); ok {
					fmt.Println(text.Text)
				}
			}
			continue
		}
		data, err := json.MarshalIndent(result.StructuredContent, "", "  ")
		if err != nil {
			return err
		}
		fmt.Println(string(data))
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
