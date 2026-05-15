import React, { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { LayoutDashboard, ListOrdered, PieChart } from "lucide-react";
import { cn } from "@/lib/utils";

interface ShellProps {
  children: React.ReactNode;
}

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: PieChart },
  { href: "/trades", label: "Trade Log", icon: ListOrdered },
];

export function Shell({ children }: ShellProps) {
  const [location] = useLocation();

  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col md:flex-row">
      <aside className="w-full md:w-64 border-r border-border bg-sidebar flex-shrink-0 flex flex-col">
        <div className="p-4 border-b border-border flex items-center h-14">
          <div className="font-mono font-bold text-primary tracking-wider uppercase flex items-center gap-2">
            <div className="w-2 h-2 bg-primary animate-pulse" />
            Trade Tracker
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto flex flex-row md:flex-col gap-2 md:gap-0">
          {navItems.map((item) => {
            const isActive = location === item.href;
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="flex-1 md:flex-none">
                <div
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors cursor-pointer",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-primary"
                      : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-foreground border-l-2 border-transparent"
                  )}
                >
                  <Icon className="w-4 h-4" />
                  <span className="hidden md:inline">{item.label}</span>
                </div>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
